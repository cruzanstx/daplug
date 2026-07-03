#!/usr/bin/env python3
"""Verification loop state, completion-marker detection, and CLI execution."""

import json
import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

from paths import get_cli_logs_dir, get_repo_root
from repostate import (
    _detect_impossible_gate,
    _detect_stalled,
    _empty_repo_state_snapshot,
    _get_git_head,
    _has_real_file_changes,
    _snapshot_from_jsonable,
    _snapshot_to_jsonable,
    repo_state_delta,
    repo_state_delta_paths,
    repo_state_snapshot,
)
from sandbox import (
    BWRAP_MISSING_ERROR,
    SANDBOX_ENV_PASSTHROUGH,
    _sandbox_error_message,
    _sandbox_passthrough_env,
    build_bwrap_args,
    check_bwrap_available,
    get_sandbox_add_dirs,
    maybe_wrap_command_with_sandbox,
    raise_on_execution_error,
    resolve_sandbox_config,
    sandbox_preflight,
)

DEFAULT_COMPLETION_MARKER = "VERIFICATION_COMPLETE"
# Sentinel used to separate echoed prompt instructions from model output in CLI logs.
# Some model CLIs print the full prompt before the assistant response; this lets us
# avoid false-positive marker detection from the prompt text itself.
INSTRUCTIONS_END_SENTINEL = "DAPLUG_INSTRUCTIONS_END"
OPENCODE_RUNTIME_SESSION_VARS = {
    "OPENCODE",
    "OPENCODE_HOSTNAME",
    "OPENCODE_PORT",
    "OPENCODE_SERVER_PASSWORD",
}

DEFAULT_MAX_ITERATIONS = 3
# How often to check log for completion (seconds)
LOOP_CHECK_INTERVAL = 5
# Patterns for detecting suggested next steps in logs
NEXT_STEPS_HEADERS = [
    r"next\s+steps?:",
    r"suggested\s+(?:next\s+)?steps?:",
    r"todo:",
    r"remaining\s+(?:work|tasks?):",
    r"follow[- ]?up(?:\s+tasks?)?:"
]
NEXT_STEPS_HEADER_RE = re.compile(
    r"^\s*(?:" + "|".join(NEXT_STEPS_HEADERS) + r")\s*(?P<inline>.*)$",
    re.IGNORECASE
)
NEXT_STEPS_ITEM_RE = re.compile("^\\s*(?:\\d+[.)]|[-*]|\u2022)\\s*(.+)$")

def get_loop_state_dir() -> Path:
    """Get the directory for loop state files."""
    state_dir = Path.home() / ".claude" / "loop-state"
    state_dir.mkdir(parents=True, exist_ok=True)
    return state_dir


def get_loop_state_file(prompt_number: str) -> Path:
    """Get the state file path for a prompt's verification loop."""
    return get_loop_state_dir() / f"{prompt_number}.json"


def load_loop_state(prompt_number: str) -> Optional[dict]:
    """Load existing loop state for a prompt."""
    state_file = get_loop_state_file(prompt_number)
    if state_file.exists():
        try:
            return json.loads(state_file.read_text())
        except (json.JSONDecodeError, IOError):
            return None
    return None


def save_loop_state(state: dict) -> None:
    """Save loop state to file."""
    state["last_updated_at"] = datetime.now().isoformat()
    state_file = get_loop_state_file(state["prompt_number"])
    state_file.write_text(json.dumps(state, indent=2))


def create_loop_state(
    prompt_number: str,
    prompt_file: str,
    model: str,
    max_iterations: int,
    completion_marker: str,
    execution_timestamp: Optional[str] = None,
    worktree_path: Optional[str] = None,
    branch_name: Optional[str] = None,
    execution_cwd: Optional[str] = None
) -> dict:
    """Create a new loop state structure."""
    return {
        "prompt_number": prompt_number,
        "prompt_file": prompt_file,
        "model": model,
        "execution_timestamp": execution_timestamp,
        "worktree_path": worktree_path,
        "branch_name": branch_name,
        "execution_cwd": execution_cwd,
        "iteration": 0,
        "max_iterations": max_iterations,
        "completion_marker": completion_marker,
        "started_at": datetime.now().isoformat(),
        "last_updated_at": datetime.now().isoformat(),
        "status": "pending",  # pending, running, completed, completed_unverified, failed, max_iterations_reached, stalled, blocked
        "history": [],
        "suggested_next_steps": [],
        "original_checkout_warnings": [],
        "require_diff": False,
        "start_snapshot": None,   # JSON-serializable repo_state_snapshot at loop start
        "start_head": None,      # git HEAD hash at loop start (for commit detection)
    }


def validate_execution_cwd(execution_cwd: str) -> tuple[bool, Optional[str]]:
    """Validate that an execution working directory exists and is a directory."""
    try:
        path = Path(execution_cwd)
    except TypeError:
        return False, f"execution_cwd is not a valid path: {execution_cwd!r}"

    if not path.exists():
        return False, f"execution_cwd does not exist: {execution_cwd}"
    if not path.is_dir():
        return False, f"execution_cwd is not a directory: {execution_cwd}"
    return True, None


def update_loop_iteration(
    state: dict,
    exit_code: int,
    marker_found: bool,
    log_file: str,
    retry_reason: Optional[str] = None
) -> dict:
    """Update loop state after an iteration completes."""
    state["history"].append({
        "iteration": state["iteration"],
        "ended_at": datetime.now().isoformat(),
        "exit_code": exit_code,
        "marker_found": marker_found,
        "retry_reason": retry_reason,
        "log_file": log_file
    })

    if marker_found:
        state["status"] = "completed"
    elif state["iteration"] >= state["max_iterations"]:
        state["status"] = "max_iterations_reached"
    else:
        state["status"] = "running"

    return state


def _extract_jsonl_text_parts(content: str) -> str:
    """Extract assistant text events from JSONL logs, ignoring tool outputs."""
    text_parts: list[str] = []
    for line in content.splitlines():
        stripped = line.strip()
        if not stripped.startswith("{"):
            continue
        try:
            event = json.loads(stripped)
        except json.JSONDecodeError:
            continue
        part = event.get("part") if isinstance(event, dict) else None
        if not isinstance(part, dict) or part.get("type") != "text":
            continue
        text = part.get("text")
        if isinstance(text, str):
            text_parts.append(text)
    return "\n".join(text_parts)


def check_completion_marker(log_file: Path, marker: str) -> tuple[bool, Optional[str]]:
    """Check if the completion marker exists in the log file.

    Returns:
        tuple: (marker_found, retry_reason if NEEDS_RETRY found)

    Note: Some CLIs echo the full prompt (including marker instructions) into the log
    before the model output. To avoid false positives, we only search for markers
    after the first occurrence of INSTRUCTIONS_END_SENTINEL if present, otherwise we
    fall back to searching after </verification_protocol>.
    """
    if not log_file.exists():
        return False, None

    try:
        content = log_file.read_text()

        # OpenCode JSONL logs include tool output as JSON events. Tool reads can contain
        # literal verification examples, so prefer assistant text events when present.
        jsonl_text = _extract_jsonl_text_parts(content)
        if jsonl_text:
            search_content = jsonl_text
        else:
            # Find where the prompt instructions end - only look for markers after that point.
            sentinel_pos = content.find(INSTRUCTIONS_END_SENTINEL)
            if sentinel_pos != -1:
                search_content = content[sentinel_pos + len(INSTRUCTIONS_END_SENTINEL):]
            else:
                # Backward-compatible fallback: older prompt wrappers ended the "example marker"
                # section at </verification_protocol>.
                protocol_end = content.rfind("</verification_protocol>")
                if protocol_end != -1:
                    search_content = content[protocol_end:]
                else:
                    search_content = content

        # Check for NEEDS_RETRY marker first (takes precedence)
        # This ensures explicit retry requests are honored even if completion marker exists
        retry_pattern = r"<verification>\s*NEEDS_RETRY:\s*(.+?)\s*</verification>"
        retry_match = re.search(retry_pattern, search_content, re.IGNORECASE | re.DOTALL)
        if retry_match:
            return False, retry_match.group(1).strip()

        # Check for completion marker in verification tags only
        completion_pattern = rf"<verification>\s*{re.escape(marker)}\s*</verification>"
        if re.search(completion_pattern, search_content, re.IGNORECASE):
            return True, None

        return False, None
    except IOError:
        return False, None


def normalize_next_step_text(text: str) -> str:
    """Normalize next step text for storage and comparison."""
    cleaned = re.sub(r"\s+", " ", text.strip())
    return cleaned.strip(" .;:-")


def normalize_next_step_key(text: str) -> str:
    """Normalize next step text for deduping across iterations."""
    cleaned = re.sub(r"[^\w\s-]", "", text.lower())
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def extract_next_steps(log_file: Path) -> list[dict]:
    """Extract suggested next steps from a log file."""
    if not log_file.exists():
        return []

    try:
        content = log_file.read_text()
    except IOError:
        return []

    lines = content.splitlines()
    steps: list[dict] = []
    index = 0

    def parse_step_lines(step_lines: list[str]) -> list[dict]:
        items: list[dict] = []
        current_text_lines: list[str] = []
        current_original = ""

        def flush_current() -> None:
            nonlocal current_text_lines, current_original
            if not current_text_lines:
                current_original = ""
                return
            text = normalize_next_step_text(" ".join(current_text_lines))
            if text:
                original = current_original or text
                items.append({"text": text, "original": original})
            current_text_lines = []
            current_original = ""

        for raw in step_lines:
            if not raw.strip():
                if current_text_lines:
                    break
                continue

            item_match = NEXT_STEPS_ITEM_RE.match(raw)
            if item_match:
                flush_current()
                current_original = raw.strip()
                current_text_lines = [item_match.group(1).strip()]
                continue

            if current_text_lines:
                continuation = raw.strip()
                if continuation:
                    current_original = f"{current_original} {continuation}" if current_original else continuation
                    current_text_lines.append(continuation)
            else:
                single = raw.strip()
                if single:
                    items.append({
                        "text": normalize_next_step_text(single),
                        "original": single
                    })

        flush_current()

        deduped: list[dict] = []
        seen: set[str] = set()
        for item in items:
            text = item.get("text", "")
            if not text:
                continue
            key = normalize_next_step_key(text)
            if not key or key in seen:
                continue
            seen.add(key)
            deduped.append({"text": text, "original": item.get("original", text)})
        return deduped

    while index < len(lines):
        line = lines[index]
        header_match = NEXT_STEPS_HEADER_RE.match(line)
        if not header_match:
            index += 1
            continue

        inline = header_match.group("inline").strip()
        captured_lines: list[str] = []
        if inline:
            captured_lines.append(inline)

        index += 1
        while index < len(lines):
            current = lines[index]
            if NEXT_STEPS_HEADER_RE.match(current):
                break
            if not current.strip():
                if captured_lines:
                    break
                index += 1
                continue
            captured_lines.append(current)
            index += 1

        steps.extend(parse_step_lines(captured_lines))

    return steps


def merge_suggested_next_steps(state: dict, new_steps: list[dict], iteration: int) -> None:
    """Merge suggested next steps into loop state with dedupe."""
    existing = state.get("suggested_next_steps", [])
    seen = {normalize_next_step_key(step.get("text", "")) for step in existing}

    for step in new_steps:
        text = step.get("text", "")
        if not text:
            continue
        key = normalize_next_step_key(text)
        if not key or key in seen:
            continue
        existing.append({
            "text": text,
            "original": step.get("original", text),
            "source_iteration": iteration
        })
        seen.add(key)

    state["suggested_next_steps"] = existing


def build_previous_iteration_feedback(history: list) -> str:
    """Build a feedback block from prior retry reasons."""
    if not history:
        return ""

    feedback_lines = []
    for entry in history:
        retry_reason = entry.get("retry_reason")
        if retry_reason:
            feedback_lines.append(
                f"Iteration {entry.get('iteration')} ended with: NEEDS_RETRY: {retry_reason}"
            )

    if not feedback_lines:
        return ""

    if len(feedback_lines) > 3:
        feedback_lines = feedback_lines[-3:]

    return "<previous_iteration_feedback>\n" + "\n".join(feedback_lines) + "\n</previous_iteration_feedback>\n\n"


def wrap_prompt_with_verification_protocol(
    content: str,
    iteration: int,
    max_iterations: int,
    completion_marker: str,
    worktree_path: Optional[str] = None,
    branch_name: Optional[str] = None,
    history: Optional[list] = None,
    original_repo_root: Optional[str] = None,
    require_diff: bool = False,
) -> str:
    """Wrap prompt content with verification protocol instructions."""
    history = history or []

    # Build iteration history summary
    history_summary = "None (first iteration)" if not history else "\n".join([
        f"  - Iteration {h['iteration']}: exit_code={h['exit_code']}, marker_found={h['marker_found']}"
        for h in history[-5:]  # Last 5 iterations
    ])

    previous_feedback = build_previous_iteration_feedback(history)

    # Build worktree context
    worktree_context = ""
    if worktree_path:
        worktree_context = f"""Working in isolated worktree: {worktree_path}
Branch: {branch_name or 'unknown'}
"""

    isolation_boundary = ""
    if worktree_path and original_repo_root and Path(worktree_path).resolve() != Path(original_repo_root).resolve():
        isolation_boundary = f"""<critical_isolation_boundary>
This run is sandboxed to an isolated git worktree.

ISOLATED WORKTREE (the only place you may write): {worktree_path}
ORIGINAL CHECKOUT (DO NOT TOUCH):                {original_repo_root}

Hard rules:
- All file operations (Read, Edit, Write, Bash with redirection, etc.) MUST target paths inside the worktree.
- DO NOT read, edit, write, build against, or run shell commands inside {original_repo_root} or any path under it.
- When spawning subagents (e.g. via a `task` tool), your composed sub-prompt MUST NOT contain the original-checkout path. Substitute the worktree path instead.
- If the task description below mentions {original_repo_root} anywhere, treat that mention as a stale reference and rewrite it to {worktree_path} before acting on it or forwarding it to a subagent.
- When sandboxing is active, bwrap enforces the boundary at the OS level.
- If parent-side activity dirties the original checkout during this run, the executor logs `ORIGINAL_CHECKOUT_DIRTIED` as a warning and continues normal completion-marker handling.
</critical_isolation_boundary>

"""

    verification_wrapper = f"""<task>
{content}
</task>

{isolation_boundary}<verification_protocol>
## Verification Loop Protocol

This task uses an iterative verification loop. You may be re-run multiple times until complete.

Important:
- Each iteration sees your previous work (files, git history).
- The controller determines completion based on a required verification tag you output.
- Do not claim completion unless the task is genuinely complete.
- Current iteration: {iteration} of {max_iterations}.
{"- Your completion claims are independently verified against the file system. The completion marker will be REJECTED if no file changes (created, modified, or committed) are detected in the execution directory. Executor-injected artifacts (TASK.md, .sisyphus/) do not count." if require_diff else ""}
{"- If your NEEDS_RETRY reason cannot change between iterations (e.g., a required file is outside the isolated worktree), describe it as a blocking condition in your retry reason rather than requesting a retry, to avoid wasting iterations." if require_diff else ""}
</verification_protocol>

{previous_feedback}<environment>
{worktree_context}Previous iterations in this loop:
{history_summary}
</environment>

---
## MANDATORY: Completion Signal (Required Action)

When ALL tasks are complete and verified, you MUST output this EXACT line literally (not as an example, not inside a code block), and make it the final line of your response:

<verification>{completion_marker}</verification>

If anything is incomplete or failing, you MUST output this EXACT line (with your reason), and make it the final line of your response:

<verification>NEEDS_RETRY: [reason]</verification>

Do not output both. Do not output any other <verification> tags.
---
{INSTRUCTIONS_END_SENTINEL}
"""
    return verification_wrapper


def run_cli(
    cli_info: dict,
    content: str,
    cwd: str,
    log_file: Path,
    sandbox_config: Optional[dict] = None,
) -> dict:
    """Run CLI command in background. Returns execution info.

    Uses stdin_mode to determine how to pass prompts:
    - "dash": Use '-' as last arg, pipe content to stdin (codex)
    - "arg": Pass content as command line argument (agy/gemini/opencode)
    - "stdin": Pipe content directly to stdin (claude --print)

    If needs_pty is True, wraps command with 'script' to provide a pseudo-TTY.
    """
    if not cli_info["command"]:
        return {"status": "subagent_required"}

    if sandbox_config and sandbox_config.get("enabled") and sandbox_config.get("type") == "bubblewrap":
        if not check_bwrap_available():
            return {"status": "error", "error": BWRAP_MISSING_ERROR, "log": str(log_file)}
        preflight_error = sandbox_preflight(cli_info, sandbox_config, cwd)
        if preflight_error:
            return {"status": "error", "error": preflight_error, "log": str(log_file)}

    stdin_mode = cli_info.get("stdin_mode", "arg")
    needs_pty = cli_info.get("needs_pty", False)
    env = os.environ.copy()
    env.update(cli_info["env"])
    sandbox_env = _sandbox_passthrough_env(cli_info)
    if cli_info.get("selected_cli") == "opencode" or (cli_info.get("command") and cli_info["command"][0] == "opencode"):
        for key in OPENCODE_RUNTIME_SESSION_VARS:
            env.pop(key, None)

    log_handle = open(log_file, "w")

    # For codex-based CLIs, add sandbox permissions for common directories
    extra_args = []
    if stdin_mode == "dash" and cli_info["command"] and cli_info["command"][0] == "codex":
        extra_args = get_sandbox_add_dirs(cwd)

    try:
        if stdin_mode == "dash":
            # Codex-style: use '-' to read from stdin
            full_cmd = cli_info["command"] + extra_args + ["-"]
            full_cmd = maybe_wrap_command_with_sandbox(full_cmd, sandbox_config, extra_env=sandbox_env)
            process = subprocess.Popen(
                full_cmd,
                cwd=cwd,
                stdin=subprocess.PIPE,
                stdout=log_handle,
                stderr=subprocess.STDOUT,
                env=env,
                text=True,
                start_new_session=True
            )
            # Write prompt content to stdin and close
            if process.stdin is None:
                raise RuntimeError("CLI process stdin is unavailable in dash mode")
            process.stdin.write(content)
            process.stdin.close()
        elif stdin_mode == "stdin":
            # Claude-style: read prompt from stdin (no extra "-" arg)
            full_cmd = cli_info["command"] + extra_args
            full_cmd = maybe_wrap_command_with_sandbox(full_cmd, sandbox_config, extra_env=sandbox_env)
            process = subprocess.Popen(
                full_cmd,
                cwd=cwd,
                stdin=subprocess.PIPE,
                stdout=log_handle,
                stderr=subprocess.STDOUT,
                env=env,
                text=True,
                start_new_session=True,
            )
            if process.stdin is None:
                raise RuntimeError("CLI process stdin is unavailable in stdin mode")
            process.stdin.write(content)
            process.stdin.close()
        else:
            # argv-style CLIs (agy/gemini/opencode): pass content as the final argument.
            full_cmd = cli_info["command"] + [content]

            # Wrap with script for PTY if needed
            if needs_pty:
                import shlex
                cmd_str = " ".join(shlex.quote(arg) for arg in full_cmd)
                full_cmd = ["script", "-q", "-c", cmd_str, "/dev/null"]

            full_cmd = maybe_wrap_command_with_sandbox(full_cmd, sandbox_config, extra_env=sandbox_env)
            process = subprocess.Popen(
                full_cmd,
                cwd=cwd,
                stdout=log_handle,
                stderr=subprocess.STDOUT,
                env=env,
                text=True,
                start_new_session=True
            )
    except Exception as exc:
        log_handle.close()
        if sandbox_config and sandbox_config.get("enabled"):
            return {
                "status": "error",
                "error": _sandbox_error_message(sandbox_config, str(exc)),
                "log": str(log_file),
            }
        return {"status": "error", "error": str(exc), "log": str(log_file)}

    return {
        "status": "running",
        "pid": process.pid,
        "log": str(log_file)
    }


def run_cli_foreground(
    cli_info: dict,
    content: str,
    cwd: str,
    log_file: Path,
    sandbox_config: Optional[dict] = None,
) -> dict:
    """Run CLI command in foreground, wait for completion. Returns execution info.

    Used for verification loops where we need to wait and check completion.
    If needs_pty is True, wraps command with 'script' to provide a pseudo-TTY.
    """
    if not cli_info["command"]:
        return {"status": "subagent_required"}

    if sandbox_config and sandbox_config.get("enabled") and sandbox_config.get("type") == "bubblewrap":
        if not check_bwrap_available():
            return {
                "status": "error",
                "exit_code": 127,
                "error": BWRAP_MISSING_ERROR,
                "log": str(log_file),
            }
        preflight_error = sandbox_preflight(cli_info, sandbox_config, cwd)
        if preflight_error:
            return {
                "status": "error",
                "exit_code": 1,
                "error": preflight_error,
                "log": str(log_file),
            }

    stdin_mode = cli_info.get("stdin_mode", "arg")
    needs_pty = cli_info.get("needs_pty", False)
    env = os.environ.copy()
    env.update(cli_info["env"])
    sandbox_env = _sandbox_passthrough_env(cli_info)
    if cli_info.get("selected_cli") == "opencode" or (cli_info.get("command") and cli_info["command"][0] == "opencode"):
        for key in OPENCODE_RUNTIME_SESSION_VARS:
            env.pop(key, None)

    log_handle = open(log_file, "w")

    # For codex-based CLIs, add sandbox permissions for common directories
    extra_args = []
    if stdin_mode == "dash" and cli_info["command"] and cli_info["command"][0] == "codex":
        extra_args = get_sandbox_add_dirs(cwd)

    try:
        if stdin_mode == "dash":
            # Codex-style: use '-' to read from stdin
            full_cmd = cli_info["command"] + extra_args + ["-"]
            full_cmd = maybe_wrap_command_with_sandbox(full_cmd, sandbox_config, extra_env=sandbox_env)
            process = subprocess.Popen(
                full_cmd,
                cwd=cwd,
                stdin=subprocess.PIPE,
                stdout=log_handle,
                stderr=subprocess.STDOUT,
                env=env,
                text=True
            )
            # Write prompt content to stdin and close
            if process.stdin is None:
                raise RuntimeError("CLI process stdin is unavailable in dash mode")
            process.stdin.write(content)
            process.stdin.close()
            exit_code = process.wait()
        elif stdin_mode == "stdin":
            full_cmd = cli_info["command"] + extra_args
            full_cmd = maybe_wrap_command_with_sandbox(full_cmd, sandbox_config, extra_env=sandbox_env)
            process = subprocess.Popen(
                full_cmd,
                cwd=cwd,
                stdin=subprocess.PIPE,
                stdout=log_handle,
                stderr=subprocess.STDOUT,
                env=env,
                text=True,
            )
            if process.stdin is None:
                raise RuntimeError("CLI process stdin is unavailable in stdin mode")
            process.stdin.write(content)
            process.stdin.close()
            exit_code = process.wait()
        else:
            # argv-style CLIs (agy/gemini/opencode): pass content as the final argument.
            full_cmd = cli_info["command"] + [content]

            # Wrap with script for PTY if needed
            if needs_pty:
                import shlex
                cmd_str = " ".join(shlex.quote(arg) for arg in full_cmd)
                full_cmd = ["script", "-q", "-c", cmd_str, "/dev/null"]

            full_cmd = maybe_wrap_command_with_sandbox(full_cmd, sandbox_config, extra_env=sandbox_env)

            process = subprocess.Popen(
                full_cmd,
                cwd=cwd,
                stdout=log_handle,
                stderr=subprocess.STDOUT,
                env=env,
                text=True
            )
            exit_code = process.wait()

        log_handle.close()
        return {
            "status": "completed",
            "exit_code": exit_code,
            "log": str(log_file)
        }
    except Exception as e:
        log_handle.close()
        if sandbox_config and sandbox_config.get("enabled"):
            return {
                "status": "error",
                "error": _sandbox_error_message(sandbox_config, str(e)),
                "log": str(log_file)
            }
        return {
            "status": "error",
            "error": str(e),
            "log": str(log_file)
        }


def run_verification_loop(
    cli_info: dict,
    original_content: str,
    cwd: str,
    log_dir: Path,
    prompt_number: str,
    model: str,
    max_iterations: int,
    completion_marker: str,
    execution_timestamp: str,
    sandbox_config: Optional[dict] = None,
    worktree_path: Optional[str] = None,
    branch_name: Optional[str] = None,
    original_repo_root: Optional[str] = None,
    require_diff: bool = False,
) -> dict:
    """Run CLI in a verification loop until completion marker found or max iterations reached.

    This is the core implementation of the iterative verification system.
    """
    # Create or load existing loop state
    existing_state = load_loop_state(prompt_number)
    if existing_state and existing_state.get("status") in {"pending", "running"}:
        # Resume from existing state. Note: state["iteration"] is persisted as the
        # next iteration to run (it is incremented after each completed iteration).
        state = existing_state
        state.setdefault("history", [])
        state.setdefault("suggested_next_steps", [])
        state.setdefault("original_checkout_warnings", [])
        if not state.get("iteration"):
            state["iteration"] = 1
    else:
        # Create new state
        state = create_loop_state(
            prompt_number=prompt_number,
            prompt_file="",  # Will be set by caller
            model=model,
            max_iterations=max_iterations,
            completion_marker=completion_marker,
            execution_timestamp=execution_timestamp,
            worktree_path=worktree_path,
            branch_name=branch_name,
            execution_cwd=cwd
        )
        state["iteration"] = 1

    # Ensure the execution timestamp is a single source of truth across resumes.
    if not state.get("execution_timestamp"):
        state["execution_timestamp"] = execution_timestamp
    effective_timestamp = state["execution_timestamp"]

    # Always refresh metadata that can change across invocations (e.g. worktree conflict resolution).
    # This prevents resuming a pending/running loop with a stale path.
    state["execution_cwd"] = cwd
    if worktree_path is not None:
        state["worktree_path"] = worktree_path
    if branch_name is not None:
        state["branch_name"] = branch_name

    # Validate execution_cwd before attempting any loop execution.
    cwd_ok, cwd_error = validate_execution_cwd(state["execution_cwd"])

    loop_log = log_dir / f"{model}-{prompt_number}-loop-{effective_timestamp}.log"
    if not loop_log.exists():
        with open(loop_log, "w") as f:
            f.write("# Loop Execution Log\n")
            f.write(f"# Prompt: {prompt_number}\n")
            f.write(f"# Model: {model}\n")
            f.write(f"# Started: {effective_timestamp}\n")
            f.write(f"# Max iterations: {max_iterations}\n")
            f.write(f"# CWD: {cwd}\n")
            f.write(f"# Worktree: {worktree_path}\n")
            f.write(f"# Branch: {branch_name}\n")
            f.write("\n")

    if not cwd_ok:
        state["status"] = "failed"
        state["failure_reason"] = cwd_error
        save_loop_state(state)
        with open(loop_log, "a") as f:
            f.write(f"[Loop] ERROR: {cwd_error}\n")
        return {
            "status": "error",
            "loop_enabled": True,
            "loop_log": str(loop_log),
            "error": cwd_error,
            "state_file": str(get_loop_state_file(prompt_number)),
            "max_iterations": max_iterations,
            "completion_marker": completion_marker,
            "iterations": [],
            "final_status": "failed",
            "total_iterations": 0,
            "suggested_next_steps": state.get("suggested_next_steps", []),
        }

    state["status"] = "running"
    state["require_diff"] = require_diff

    # Capture the execution-cwd state at loop start for --require-diff.
    # This persists across resumes so the baseline is the original loop start.
    if require_diff:
        if not state.get("start_snapshot"):
            state["start_snapshot"] = _snapshot_to_jsonable(
                repo_state_snapshot(state["execution_cwd"])
            )
        if not state.get("start_head"):
            state["start_head"] = _get_git_head(state["execution_cwd"])
    save_loop_state(state)

    result = {
        "status": "running",
        "loop_enabled": True,
        "loop_log": str(loop_log),
        "max_iterations": max_iterations,
        "completion_marker": completion_marker,
        "iterations": [],
        "final_status": None,
        "original_checkout_warnings": state.get("original_checkout_warnings", []),
    }

    while state["iteration"] <= max_iterations:
        iteration = state["iteration"]
        execution_cwd = state.get("execution_cwd") or cwd

        cwd_ok, cwd_error = validate_execution_cwd(execution_cwd)
        if not cwd_ok:
            state["status"] = "failed"
            state["failure_reason"] = cwd_error
            save_loop_state(state)
            with open(loop_log, "a") as f:
                f.write(f"[Loop] ERROR: {cwd_error}\n")
            result["final_status"] = "failed"
            result["status"] = "error"
            result["error"] = cwd_error
            break

        log_file = log_dir / f"{model}-{prompt_number}-iter{iteration}-{effective_timestamp}.log"

        # Wrap content with verification protocol
        wrapped_content = wrap_prompt_with_verification_protocol(
            content=original_content,
            iteration=iteration,
            max_iterations=max_iterations,
            completion_marker=completion_marker,
            worktree_path=worktree_path,
            branch_name=branch_name,
            history=state["history"],
            original_repo_root=original_repo_root,
            require_diff=require_diff,
        )

        print(f"[Loop] Starting iteration {iteration}/{max_iterations}...", file=sys.stderr)
        with open(loop_log, "a") as f:
            f.write(f"[Loop] Starting iteration {iteration}/{max_iterations}\n")
            f.write(f"[Loop] Iteration log: {log_file}\n")

        # Snapshot the original (non-worktree) repo so parent-side dirtiness can be logged.
        guard_active = bool(
            worktree_path
            and original_repo_root
            and Path(worktree_path).resolve() != Path(original_repo_root).resolve()
        )
        guard_repo_root = original_repo_root if guard_active and original_repo_root else None
        pre_status = repo_state_snapshot(guard_repo_root) if guard_repo_root else _empty_repo_state_snapshot()

        # Run CLI and wait for completion
        if sandbox_config and sandbox_config.get("enabled"):
            exec_result = run_cli_foreground(
                cli_info,
                wrapped_content,
                execution_cwd,
                log_file,
                sandbox_config=sandbox_config,
            )
        else:
            exec_result = run_cli_foreground(cli_info, wrapped_content, execution_cwd, log_file)

        if exec_result.get("status") == "error":
            error_msg = exec_result.get("error", "Unknown execution error")
            with open(loop_log, "a") as f:
                f.write(f"[Loop] ERROR: {error_msg}\n")
            state["status"] = "failed"
            state["failure_reason"] = error_msg
            save_loop_state(state)
            result["final_status"] = "failed"
            result["status"] = "error"
            result["error"] = error_msg
            break

        # The sandbox is the security boundary. Original checkout changes observed here
        # are logged for operator awareness, but they do not invalidate the iteration.
        if guard_repo_root:
            post_status = repo_state_snapshot(guard_repo_root)
            if post_status != pre_status:
                delta = repo_state_delta(pre_status, post_status)
                changed_paths = repo_state_delta_paths(delta)
                shown_paths = changed_paths[:20]
                path_summary = ", ".join(shown_paths) if shown_paths else "<unknown>"
                if len(changed_paths) > len(shown_paths):
                    path_summary += f", ... ({len(changed_paths) - len(shown_paths)} more)"
                warning = {
                    "iteration": iteration,
                    "modified": delta["modified"],
                    "new_untracked": delta["new_untracked"],
                    "removed_untracked": delta["removed_untracked"],
                }
                state.setdefault("original_checkout_warnings", []).append(warning)
                result["original_checkout_warnings"] = state["original_checkout_warnings"]
                with open(loop_log, "a") as f:
                    f.write(
                        "[Loop] ORIGINAL_CHECKOUT_DIRTIED: "
                        f"original checkout changed during iteration {iteration}; "
                        f"paths: {path_summary}\n"
                    )
                save_loop_state(state)

        # Check for completion marker
        marker_found, retry_reason = check_completion_marker(log_file, completion_marker)

        # --require-diff: verify the execution cwd actually changed before accepting
        # the completion marker.  If not, reject and convert to a synthetic retry so
        # the model gets feedback and another chance (issue #14).
        diff_rejected = False
        if marker_found and require_diff:
            after_snapshot = repo_state_snapshot(execution_cwd)
            after_head = _get_git_head(execution_cwd)
            before_snapshot = _snapshot_from_jsonable(state.get("start_snapshot"))
            before_head = state.get("start_head")
            if not _has_real_file_changes(
                before_snapshot, after_snapshot, before_head, after_head,
            ):
                marker_found = False
                retry_reason = (
                    "completion marker found but no file changes detected (--require-diff)"
                )
                diff_rejected = True
                print(
                    "[Loop] Completion marker rejected (--require-diff): "
                    "no file changes detected",
                    file=sys.stderr,
                )
                with open(loop_log, "a") as f:
                    f.write(
                        "[Loop] Completion marker rejected (--require-diff): "
                        "no file changes detected\n"
                    )

        # Extract suggested next steps from this iteration's log
        next_steps = extract_next_steps(log_file)
        if next_steps:
            merge_suggested_next_steps(state, next_steps, iteration)

        # Update state
        exit_code = exec_result.get("exit_code", -1)
        state = update_loop_iteration(
            state,
            exit_code,
            marker_found,
            str(log_file),
            retry_reason=retry_reason
        )

        iteration_result = {
            "iteration": iteration,
            "log_file": str(log_file),
            "exit_code": exit_code,
            "marker_found": marker_found,
            "retry_reason": retry_reason
        }
        result["iterations"].append(iteration_result)

        if marker_found:
            print(f"[Loop] Completion marker found at iteration {iteration}!", file=sys.stderr)
            with open(loop_log, "a") as f:
                f.write(f"[Loop] Completed at iteration {iteration}\n")
            state["status"] = "completed"
            save_loop_state(state)
            result["final_status"] = "completed"
            result["status"] = "completed"
            break

        # Dead-loop detection (always on, no flag).
        if retry_reason:
            print(f"[Loop] Retry requested: {retry_reason}", file=sys.stderr)
            with open(loop_log, "a") as f:
                f.write(f"[Loop] NEEDS_RETRY: {retry_reason}\n")

            # Impossible-gate detection: abort immediately on the FIRST occurrence
            # (issue #18 — retrying will never fix an isolation-boundary refusal).
            if _detect_impossible_gate(retry_reason, execution_cwd):
                failure_reason = (
                    f"Retry reason indicates an impossible gate that no retry can fix: "
                    f"{retry_reason}"
                )
                suggested = (
                    "the prompt requires resources unavailable under --worktree isolation; "
                    "re-run without --worktree or copy the required file into the repo"
                )
                state["status"] = "blocked"
                state["failure_reason"] = failure_reason
                state.setdefault("suggested_next_steps", []).append({
                    "text": suggested,
                    "original": suggested,
                    "source_iteration": iteration,
                })
                save_loop_state(state)
                with open(loop_log, "a") as f:
                    f.write(f"[Loop] BLOCKED: impossible gate detected: {retry_reason}\n")
                    f.write(f"[Loop] Suggested next step: {suggested}\n")
                result["final_status"] = "blocked"
                result["status"] = "blocked"
                result["failure_reason"] = failure_reason
                result["suggested_next_steps"] = state.get("suggested_next_steps", [])
                break

            # Stalled detection: two consecutive identical retry_reasons mean no
            # progress is possible — abort instead of burning more iterations.
            if _detect_stalled(state["history"]):
                failure_reason = (
                    f"Repeated identical retry reasons indicate no progress is possible: "
                    f"{retry_reason}"
                )
                state["status"] = "stalled"
                state["failure_reason"] = failure_reason
                save_loop_state(state)
                with open(loop_log, "a") as f:
                    f.write(
                        f"[Loop] STALLED: repeated identical retry reason: "
                        f"{retry_reason}\n"
                    )
                result["final_status"] = "stalled"
                result["status"] = "stalled"
                result["failure_reason"] = failure_reason
                break

        if state["iteration"] >= max_iterations:
            if diff_rejected:
                # Marker was found but rejected by --require-diff on the final
                # iteration — distinct from both "completed" and "max_iterations".
                state["status"] = "completed_unverified"
                save_loop_state(state)
                print(
                    "[Loop] Completed unverified: marker found but no file changes "
                    "(--require-diff), max iterations reached",
                    file=sys.stderr,
                )
                with open(loop_log, "a") as f:
                    f.write(
                        "[Loop] Completed unverified: marker found but no file changes "
                        "(--require-diff), max iterations reached\n"
                    )
                result["final_status"] = "completed_unverified"
                result["status"] = "completed_unverified"
            else:
                print(f"[Loop] Max iterations ({max_iterations}) reached without completion.", file=sys.stderr)
                with open(loop_log, "a") as f:
                    f.write(f"[Loop] Max iterations reached ({max_iterations})\n")
                state["status"] = "max_iterations_reached"
                save_loop_state(state)
                result["final_status"] = "max_iterations_reached"
                result["status"] = "max_iterations_reached"
            break

        # Prepare for next iteration
        state["iteration"] += 1
        save_loop_state(state)
        print(f"[Loop] Preparing for iteration {state['iteration']}...", file=sys.stderr)
        with open(loop_log, "a") as f:
            f.write(f"[Loop] Preparing for iteration {state['iteration']}\n")

    result["state_file"] = str(get_loop_state_file(prompt_number))
    result["total_iterations"] = len(result["iterations"])
    result["suggested_next_steps"] = state.get("suggested_next_steps", [])
    result["original_checkout_warnings"] = state.get("original_checkout_warnings", [])
    if state.get("failure_reason"):
        result["failure_reason"] = state["failure_reason"]
    return result


def run_verification_loop_background(
    cli_info: dict,
    original_content: str,
    cwd: str,
    log_dir: Path,
    prompt_number: str,
    model: str,
    max_iterations: int,
    completion_marker: str,
    execution_timestamp: str,
    worktree_path: Optional[str] = None,
    branch_name: Optional[str] = None,
    cli_override: Optional[str] = None,
    variant: Optional[str] = None,
    sandbox_enabled: bool = False,
    sandbox_type: Optional[str] = None,
    sandbox_profile: str = "balanced",
    sandbox_workspace: Optional[str] = None,
    sandbox_net: Optional[str] = None,
    original_repo_root: Optional[str] = None,
    require_diff: bool = False,
) -> dict:
    """Start a verification loop in background mode.

    Returns immediately with PID. The loop runs as a separate process.
    """
    cwd_ok, cwd_error = validate_execution_cwd(cwd)
    if not cwd_ok:
        state = create_loop_state(
            prompt_number=prompt_number,
            prompt_file="",
            model=model,
            max_iterations=max_iterations,
            completion_marker=completion_marker,
            execution_timestamp=execution_timestamp,
            worktree_path=worktree_path,
            branch_name=branch_name,
            execution_cwd=cwd,
        )
        state["status"] = "failed"
        state["failure_reason"] = cwd_error
        save_loop_state(state)

        loop_log = log_dir / f"{model}-{prompt_number}-loop-{execution_timestamp}.log"
        with open(loop_log, "w") as f:
            f.write("# Loop Execution Log\n")
            f.write(f"# Prompt: {prompt_number}\n")
            f.write(f"# Model: {model}\n")
            f.write(f"# Started: {execution_timestamp}\n")
            f.write(f"# Max iterations: {max_iterations}\n")
            f.write(f"# CWD: {cwd}\n")
            f.write(f"# Worktree: {worktree_path}\n")
            f.write(f"# Branch: {branch_name}\n")
            f.write(f"\n")
            f.write(f"[Loop] ERROR: {cwd_error}\n")

        return {
            "status": "error",
            "error": cwd_error,
            "loop_log": str(loop_log),
            "state_file": str(get_loop_state_file(prompt_number)),
            "max_iterations": max_iterations,
            "completion_marker": completion_marker,
        }

    # Create initial loop state
    state = create_loop_state(
        prompt_number=prompt_number,
        prompt_file="",
        model=model,
        max_iterations=max_iterations,
        completion_marker=completion_marker,
        execution_timestamp=execution_timestamp,
        worktree_path=worktree_path,
        branch_name=branch_name,
        execution_cwd=cwd
    )
    save_loop_state(state)

    loop_log = log_dir / f"{model}-{prompt_number}-loop-{execution_timestamp}.log"

    # Build command to run this script with --loop-foreground flag
    script_path = Path(__file__).resolve().parent / "executor.py"
    cmd = [
        sys.executable, str(script_path),
        "--model", model,
        "--run",
        "--loop",
        "--max-iterations", str(max_iterations),
        "--completion-marker", completion_marker,
        "--execution-timestamp", execution_timestamp,
        "--loop-foreground"  # Internal flag to run in foreground mode
    ]
    if cli_override:
        cmd.extend(["--cli", cli_override])
    if variant is not None:
        cmd.extend(["--variant", variant])
    if sandbox_enabled:
        cmd.append("--sandbox")
    if sandbox_type:
        cmd.extend(["--sandbox-type", sandbox_type])
    if sandbox_profile:
        cmd.extend(["--sandbox-profile", sandbox_profile])
    if sandbox_workspace:
        cmd.extend(["--sandbox-workspace", sandbox_workspace])
    if sandbox_net:
        cmd.extend(["--sandbox-net", sandbox_net])
    if original_repo_root:
        cmd.extend(["--original-repo-root", original_repo_root])
    if require_diff:
        cmd.append("--require-diff")

    if worktree_path:
        # When in worktree, use --prompt-file to read TASK.md directly
        # This avoids the issue where prompts/ directory doesn't exist in worktree
        task_file = Path(worktree_path) / "TASK.md"
        cmd.extend([
            "--prompt-file", str(task_file),
            "--prompt-number", prompt_number,
            "--cwd", cwd,
            # Forward worktree context so the foreground re-entry can re-activate
            # the isolation guard and the <critical_isolation_boundary> wrapper.
            # Without these, args.worktree=False inside the re-entry and both
            # defenses silently disable. (See smoke regression in tests.)
            "--worktree-path", worktree_path,
        ])
        if branch_name:
            cmd.extend(["--branch-name", branch_name])
    else:
        # Normal mode: resolve prompt by number
        cmd.append(prompt_number)

    # Write initial metadata to loop log before starting subprocess
    with open(loop_log, "w") as f:
        f.write(f"# Loop Execution Log\n")
        f.write(f"# Prompt: {prompt_number}\n")
        f.write(f"# Model: {model}\n")
        f.write(f"# Started: {execution_timestamp}\n")
        f.write(f"# Max iterations: {max_iterations}\n")
        f.write(f"# CWD: {cwd}\n")
        f.write(f"# Worktree: {worktree_path}\n")
        f.write(f"# Branch: {branch_name}\n")
        f.write(f"\n")

    # Start background process
    # Use append mode so subprocess output is added after initial metadata
    log_handle = open(loop_log, "a")
    process = subprocess.Popen(
        cmd,
        cwd=cwd,
        stdout=log_handle,
        stderr=subprocess.STDOUT,
        start_new_session=True
    )

    return {
        "status": "loop_running",
        "pid": process.pid,
        "loop_log": str(loop_log),
        "state_file": str(get_loop_state_file(prompt_number)),
        "max_iterations": max_iterations,
        "completion_marker": completion_marker
    }
