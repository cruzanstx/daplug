#!/usr/bin/env python3
"""
Prompt Executor - Prompt resolution, optional worktree creation, and CLI launching.

Resolves prompts from ./prompts/, optionally creates isolated git worktrees,
and launches AI CLI tools. Supports iterative verification loops.

This module is the CLI entry point and a re-export facade over the focused
sub-modules (paths, repostate, worktree, models, sandbox, loop).  Tests and
external consumers do ``import executor`` and reference ``executor.<name>``;
every historically-public name remains accessible through the re-exports below.
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

# Make sibling modules importable when this file is loaded via importlib
# (several test files use spec_from_file_location without adding the scripts
# directory to sys.path).
_SCRIPTS_DIR = str(Path(__file__).resolve().parent)
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)


from paths import (
    _read_config_value,
    detect_default_branch,
    get_cli_logs_dir,
    get_repo_root,
    get_worktree_dir,
)
from repostate import (
    _EXECUTOR_ARTIFACT_PATHS,
    _EXECUTOR_ARTIFACT_PREFIXES,
    _IMPOSSIBLE_GATE_PHRASES,
    _detect_impossible_gate,
    _detect_stalled,
    _empty_repo_state_snapshot,
    _get_git_head,
    _has_real_file_changes,
    _is_executor_artifact,
    _normalize_retry_reason,
    _run_snapshot_git,
    _snapshot_from_jsonable,
    _snapshot_timeout,
    _snapshot_to_jsonable,
    _split_nul_paths,
    repo_state_delta,
    repo_state_delta_paths,
    repo_state_snapshot,
)
from worktree import (
    create_worktree,
    ensure_worktree_permissions,
    get_existing_worktree,
    install_worktree_dependencies,
    normalize_worktree_path,
)
from models import (
    CLI_OVERRIDE_SUPPORTED_MODELS,
    CODEX_REASONING_VARIANTS,
    FORCE_DIRECT_OPENCODE_MODELS,
    GOOGLE_MODEL_SHORTHANDS,
    LEGACY_MODEL_DISPLAY,
    MODEL_ALIAS_BASE,
    MODEL_ALIAS_DEFAULT_VARIANT,
    MODEL_CHOICES,
    MODEL_REGISTRY,
    MODEL_REGISTRY_BY_NAME,
    MODEL_REGISTRY_PATH,
    MODEL_SPECS,
    ModelRegistryError,
    SUPPORTED_VARIANTS,
    SYNTHETIC_MODEL_SHORTHANDS,
    _ALLOWED_STDIN_MODES,
    _ExecutionConfig,
    _REQUIRED_MODEL_FIELDS,
    _RUNTIME_SPEC_FIELDS,
    _agy_model_arg,
    _build_agy_command,
    _build_claude_command,
    _build_codex_command,
    _build_gemini_command,
    _build_opencode_command,
    _canonical_model,
    _claude_cli_command,
    _cli_info_from_router,
    _dynamic_display,
    _env_for_command,
    _load_model_registry,
    _normalize_cli_override,
    _normalize_preferred_agent,
    _normalize_variant,
    _opencode_model_spec,
    _registry_runtime,
    _require_claude_cli,
    _require_synthetic_api_key,
    _resolve_router_command,
    _strip_provider_prefix,
    _validate_cli_override,
    get_cli_info,
)
from sandbox import (
    BWRAP_MISSING_ERROR,
    BWRAP_PROFILES,
    SANDBOX_ENV_PASSTHROUGH,
    SANDBOX_PREFLIGHT_TIMEOUT,
    _SANDBOX_PREFLIGHT_CACHE,
    _existing_paths,
    _node_version_root,
    _path_within,
    _sandbox_config_summary,
    _sandbox_error_message,
    _sandbox_passthrough_env,
    _selected_cli_runtime_paths,
    build_bwrap_args,
    check_bwrap_available,
    get_sandbox_add_dirs,
    maybe_wrap_command_with_sandbox,
    raise_on_execution_error,
    resolve_sandbox_config,
    sandbox_preflight,
)
from loop import (
    DEFAULT_COMPLETION_MARKER,
    DEFAULT_MAX_ITERATIONS,
    INSTRUCTIONS_END_SENTINEL,
    LOOP_CHECK_INTERVAL,
    NEXT_STEPS_HEADERS,
    NEXT_STEPS_HEADER_RE,
    NEXT_STEPS_ITEM_RE,
    OPENCODE_RUNTIME_SESSION_VARS,
    _extract_jsonl_text_parts,
    build_previous_iteration_feedback,
    check_completion_marker,
    create_loop_state,
    extract_next_steps,
    get_loop_state_dir,
    get_loop_state_file,
    load_loop_state,
    merge_suggested_next_steps,
    normalize_next_step_key,
    normalize_next_step_text,
    run_cli,
    run_cli_foreground,
    run_verification_loop,
    run_verification_loop_background,
    save_loop_state,
    update_loop_iteration,
    validate_execution_cwd,
    wrap_prompt_with_verification_protocol,
)


def extract_prompt_title(content: str) -> str:
    """Extract title from prompt content.

    Looks for:
    1. First markdown header (# Title)
    2. First non-empty line if no header
    """
    lines = content.strip().split('\n')
    for line in lines:
        line = line.strip()
        if not line:
            continue
        # Check for markdown header
        if line.startswith('#'):
            # Remove # prefix and clean up
            return line.lstrip('#').strip()
        # Use first non-empty line as title (truncated)
        return line[:80] + ('...' if len(line) > 80 else '')
    return "Untitled prompt"


def expand_prompt_input(prompt_input: str) -> list[str]:
    """Expand ranges and comma-separated lists into individual prompt identifiers.

    Examples:
        "002-005" -> ["002", "003", "004", "005"]
        "002,005,007" -> ["002", "005", "007"]
        "002-004,010,015-017" -> ["002", "003", "004", "010", "015", "016", "017"]
        "providers/011-013" -> ["providers/011", "providers/012", "providers/013"]
        "001,providers/011,020" -> ["001", "providers/011", "020"]
        "fix-bug" -> ["fix-bug"]  (no expansion, treated as name)
    """
    results = []

    # Split by comma first
    parts = prompt_input.split(",")

    for part in parts:
        part = part.strip()
        if not part:
            continue

        # Check for range pattern (optionally folder-prefixed): "<folder>/001-010" or "001-010"
        range_match = re.match(r'^(?:(?P<folder>.+)/)?(?P<start>\d+)-(?P<end>\d+)$', part)
        if range_match:
            folder = range_match.group("folder")
            start_raw, end_raw = range_match.group("start"), range_match.group("end")
            start, end = int(start_raw), int(end_raw)
            if start > end:
                start, end = end, start  # Allow reverse ranges
            # Preserve zero-padding from the larger number
            width = max(len(start_raw), len(end_raw), 3)
            for n in range(start, end + 1):
                num = str(n).zfill(width)
                results.append(f"{folder}/{num}" if folder else num)
        else:
            results.append(part)

    return results if results else [prompt_input]


def resolve_prompt(prompts_dir: Path, prompt_input: str) -> Path:
    """Resolve a single prompt input to file path."""
    completed_dir = prompts_dir / "completed"

    def _normalize_folder(value: str) -> str:
        cleaned = value.strip().replace("\\", "/").strip("/")
        parts = [p for p in cleaned.split("/") if p and p != "."]
        if any(p == ".." for p in parts):
            raise ValueError(f"Invalid folder path (path traversal not allowed): {value}")
        return "/".join(parts)

    def _iter_prompt_files(search_root: Path, include_completed: bool) -> list[Path]:
        files: list[Path] = []
        for file in search_root.rglob("*.md"):
            if not file.is_file():
                continue
            if file.name.startswith("_"):
                continue
            if not include_completed and completed_dir in file.parents:
                continue
            files.append(file)
        return files

    folder_filter: str | None = None
    token = prompt_input.strip()
    if "/" in token:
        folder_part, token = token.rsplit("/", 1)
        folder_filter = _normalize_folder(folder_part)
        token = token.strip()

    # Determine search root and whether to include completed/
    if folder_filter is None:
        search_root = prompts_dir
        include_completed = False
    else:
        search_root = prompts_dir / folder_filter if folder_filter else prompts_dir
        if not search_root.exists() or not search_root.is_dir():
            raise FileNotFoundError(f"No prompt folder: {folder_filter}")
        include_completed = folder_filter == "completed" or folder_filter.startswith("completed/")

    files = _iter_prompt_files(search_root, include_completed=include_completed)

    # Try as number (e.g., "123" -> "123-*.md")
    if token.isdigit():
        padded = token.zfill(3)
        matches = [f for f in files if f.name.startswith(f"{padded}-")]
        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            rels = [str(m.relative_to(prompts_dir)) for m in matches]
            raise ValueError(f"Ambiguous prompt '{prompt_input}': {rels}")
        raise FileNotFoundError(f"No prompt found for '{prompt_input}'")

    # Try as partial name match
    matches = [f for f in files if token.lower() in f.name.lower()]

    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        rels = [str(m.relative_to(prompts_dir)) for m in matches]
        raise ValueError(f"Ambiguous prompt '{prompt_input}': {rels}")

    raise FileNotFoundError(f"No prompt found for '{prompt_input}'")


def resolve_prompts(prompts_dir: Path, prompt_inputs: list[str]) -> list[Path]:
    """Resolve prompt inputs to file paths.

    Supports ranges and comma-separated lists:
        "002-005" -> prompts 002, 003, 004, 005
        "002,005,007" -> prompts 002, 005, 007
        "002-004,010" -> prompts 002, 003, 004, 010
    """
    if not prompts_dir.exists():
        raise FileNotFoundError(f"No prompts directory: {prompts_dir}")

    # No input = latest prompt
    if not prompt_inputs:
        completed_dir = prompts_dir / "completed"
        prompt_files = [
            p for p in prompts_dir.rglob("*.md")
            if p.is_file()
            and not p.name.startswith("_")
            and completed_dir not in p.parents
        ]
        prompt_files = sorted(prompt_files, key=lambda p: p.stat().st_mtime)
        if not prompt_files:
            raise FileNotFoundError("No prompt files found")
        return [prompt_files[-1]]

    # Filter out flags, then expand ranges/comma-lists
    inputs = [p for p in prompt_inputs if not p.startswith("-")]
    expanded = []
    for inp in inputs:
        expanded.extend(expand_prompt_input(inp))

    # Deduplicate while preserving order
    seen = set()
    unique = []
    for item in expanded:
        if item not in seen:
            seen.add(item)
            unique.append(item)

    return [resolve_prompt(prompts_dir, inp) for inp in unique]


def main():
    parser = argparse.ArgumentParser(description="Resolve and execute prompts")
    parser.add_argument("prompts", nargs="*", default=[], help="Prompt number(s) or name(s)")
    parser.add_argument("--model", "-m", default="claude",
                       choices=list(MODEL_CHOICES),
                       help="Model/CLI to use")
    parser.add_argument("--cli", choices=["codex", "opencode", "claude", "claudecode", "cc", "agy", "antigravity", "gemini"],
                       default=None,
                       help="Override CLI wrapper (default: auto-detected per model)")
    parser.add_argument(
        "--variant",
        choices=list(SUPPORTED_VARIANTS),
        default=None,
        help=(
            "Reasoning variant: none|low|medium|high|xhigh. "
            "Explicit --variant overrides alias defaults (for example codex-high)."
        ),
    )
    parser.add_argument("--cwd", "-c", default=None,
                       help="Working directory for execution")
    parser.add_argument("--run", "-r", action="store_true",
                       help="Actually run the CLI (default: just return info)")
    parser.add_argument("--info-only", "-i", action="store_true",
                       help="Only return prompt info, no CLI details")
    parser.add_argument("--worktree", "-w", action="store_true",
                       help="Create isolated git worktree for execution")
    parser.add_argument("--sandbox", action="store_true",
                       help="Enable sandboxing (Linux default backend: bubblewrap)")
    parser.add_argument("--sandbox-type", choices=["bubblewrap"], default=None,
                       help="Sandbox backend override")
    parser.add_argument("--no-sandbox", action="store_true",
                       help="Explicitly disable sandboxing")
    parser.add_argument("--sandbox-profile", choices=["strict", "balanced", "dev"], default="balanced",
                       help="Sandbox profile preset (default: balanced)")
    parser.add_argument("--sandbox-workspace", default=None,
                       help="Sandbox workspace path override (default: execution cwd)")
    parser.add_argument("--sandbox-net", choices=["on", "off"], default=None,
                       help="Sandbox network mode override")
    parser.add_argument("--base-branch", "-b", default=None,
                       help="Base branch for worktree (default: auto-detect from origin/HEAD, "
                            "falling back to the current branch and then 'main')")
    parser.add_argument("--original-repo-root", default=None,
                       help="Original (non-worktree) repo root, used to enforce the worktree "
                            "isolation guard during --loop runs. Forwarded automatically when "
                            "the background loop re-launches itself.")
    parser.add_argument("--worktree-path", default=None,
                       help="Internal flag: existing worktree path, forwarded by the background "
                            "loop spawner so the foreground re-entry can run the isolation guard "
                            "and inject the boundary warning without re-creating the worktree.")
    parser.add_argument("--branch-name", default=None,
                       help="Internal flag: worktree branch name, forwarded alongside --worktree-path.")
    parser.add_argument("--on-conflict", default="error",
                       choices=["error", "remove", "reuse", "increment"],
                       help="How to handle existing worktree: error (return conflict info), "
                            "remove (delete and recreate), reuse (use existing), "
                            "increment (create with -1, -2 suffix)")

    # Verification loop arguments
    parser.add_argument("--loop", "-l", action="store_true",
                       help="Enable iterative verification loop until completion")
    parser.add_argument("--max-iterations", type=int, default=DEFAULT_MAX_ITERATIONS,
                       help=f"Max iterations before giving up (default: {DEFAULT_MAX_ITERATIONS})")
    parser.add_argument("--completion-marker", default=DEFAULT_COMPLETION_MARKER,
                       help=f"Text pattern that signals completion (default: {DEFAULT_COMPLETION_MARKER})")
    parser.add_argument("--require-diff", action="store_true",
                       help="Reject the completion marker when no file changes (created, modified, "
                            "or committed) are detected in the execution directory. "
                            "Excludes executor-injected artifacts (TASK.md, .sisyphus/).")
    parser.add_argument("--loop-foreground", action="store_true",
                       help="Internal flag: run loop in foreground (used by background spawner)")
    parser.add_argument("--loop-status", action="store_true",
                       help="Check status of an existing verification loop")
    parser.add_argument("--prompt-file", type=str, default=None,
                       help="Read prompt content from file instead of resolving by number (used for worktree loops)")
    parser.add_argument("--prompt-number", type=str, default=None,
                       help="Prompt number to use with --prompt-file (for state/log naming)")
    parser.add_argument(
        "--execution-timestamp",
        type=str,
        default=None,
        help=argparse.SUPPRESS,
    )

    args = parser.parse_args()

    try:
        repo_root = get_repo_root()
        prompts_dir = repo_root / "prompts"
        default_execution_cwd = args.cwd or str(repo_root)
        sandbox_config = resolve_sandbox_config(sys.platform, args, default_execution_cwd)

        # Handle --loop-status: check status of existing loop
        if args.loop_status:
            if not args.prompts:
                # List all active loops
                state_dir = get_loop_state_dir()
                states = []
                for state_file in state_dir.glob("*.json"):
                    try:
                        state = json.loads(state_file.read_text())
                        states.append(state)
                    except (json.JSONDecodeError, IOError):
                        pass
                print(json.dumps({"loop_states": states}, indent=2))
            else:
                # Check specific prompt's loop status
                raw = args.prompts[0].strip()
                token = raw.rsplit("/", 1)[-1]
                if not token.isdigit():
                    print(json.dumps({"error": f"Invalid prompt for --loop-status: {raw}"}))
                    return
                prompt_num = token.zfill(3)
                state = load_loop_state(prompt_num)
                if state:
                    print(json.dumps({"loop_state": state}, indent=2))
                else:
                    print(json.dumps({"error": f"No loop state found for prompt {prompt_num}"}))
            return

        # Handle --prompt-file: read from specific file instead of resolving
        if args.prompt_file:
            prompt_file_path = Path(args.prompt_file)
            if not prompt_file_path.exists():
                raise FileNotFoundError(f"Prompt file not found: {args.prompt_file}")
            prompt_files = [prompt_file_path]
        else:
            prompt_files = resolve_prompts(prompts_dir, args.prompts)

        cli_info = get_cli_info(
            args.model,
            repo_root=repo_root,
            cli_override=args.cli,
            variant=args.variant,
        )
        log_dir = get_cli_logs_dir(repo_root)
        log_dir.mkdir(parents=True, exist_ok=True)

        execution_timestamp = args.execution_timestamp or datetime.now().strftime("%Y%m%d-%H%M%S")

        result = {
            "repo": repo_root.name,
            "model": args.model,
            "cli_display": cli_info["display"],
            "cli_command": maybe_wrap_command_with_sandbox(cli_info.get("command"), sandbox_config),
            "selected_cli": cli_info.get("selected_cli"),
            "variant": cli_info.get("variant"),
            "stdin_mode": cli_info.get("stdin_mode"),
            "sandbox": sandbox_config,
            "prompts": []
        }

        # Add loop info to result if loop mode enabled
        if args.loop:
            result["loop_mode"] = True
            result["max_iterations"] = args.max_iterations
            result["completion_marker"] = args.completion_marker
            result["require_diff"] = args.require_diff

        for prompt_file in prompt_files:
            # Use --prompt-number if provided (for worktree loops), otherwise extract from filename
            if args.prompt_number:
                prompt_num = args.prompt_number.zfill(3)
            else:
                prompt_num = prompt_file.stem.split("-")[0]
            log_file = log_dir / f"{args.model}-{prompt_num}-{execution_timestamp}.log"

            content = prompt_file.read_text()

            # Folder/path metadata (supports prompts/ subfolders)
            folder = ""
            status = "active"
            try:
                rel_to_prompts = prompt_file.relative_to(prompts_dir)
                folder_path = rel_to_prompts.parent
                folder = "" if folder_path == Path(".") else folder_path.as_posix()
                if folder == "completed" or folder.startswith("completed/"):
                    status = "completed"
            except ValueError:
                folder = ""
                status = "active"

            try:
                rel_to_repo = prompt_file.relative_to(repo_root)
                prompt_repo_path = rel_to_repo.as_posix()
            except ValueError:
                prompt_repo_path = str(prompt_file)

            prompt_info = {
                "file": str(prompt_file),
                "path": prompt_repo_path,
                "name": prompt_file.name,
                "number": prompt_num,
                "folder": folder,
                "status": status,
                "title": extract_prompt_title(content),
                "content": content,
                "log": str(log_file)
            }

            # Resolve the original (non-worktree) repo root for the isolation guard.
            # Explicit --original-repo-root wins (set by background loop re-entry from
            # within the worktree); otherwise the current repo_root is correct.
            original_repo_root = args.original_repo_root or str(repo_root)

            # Create worktree if requested
            worktree_path = None
            branch_name = None
            if args.worktree:
                worktree_info = create_worktree(repo_root, prompt_file, args.base_branch,
                                                args.on_conflict)
                prompt_info["worktree"] = worktree_info

                # Check for conflict - don't proceed with execution
                if worktree_info.get("conflict"):
                    result["prompts"].append(prompt_info)
                    continue

                # Use worktree as cwd for execution
                execution_cwd = worktree_info["worktree_path"]
                worktree_path = worktree_info["worktree_path"]
                branch_name = worktree_info.get("branch_name")
            elif args.worktree_path:
                # Loop-foreground re-entry: the spawner already created the worktree
                # and is forwarding its path so we can re-activate the isolation
                # guard and the boundary wrapper without re-creating anything.
                worktree_path = args.worktree_path
                branch_name = args.branch_name
                execution_cwd = args.cwd or args.worktree_path

                # Claude Task subagents rely on global Claude Code permissions.
                # Ensure the (potentially out-of-repo) worktree path is permitted before execution.
                if (
                    args.run
                    and args.model == "claude"
                    and cli_info.get("stdin_mode") is None
                    and worktree_path
                ):
                    try:
                        ensure_worktree_permissions(worktree_path, str(repo_root))
                    except Exception as exc:
                        print(
                            f"[Claude] Warning: failed to update ~/.claude/settings.json for worktree permissions: {exc}",
                            file=sys.stderr,
                        )
            else:
                execution_cwd = args.cwd or str(repo_root)

            prompt_sandbox_config = resolve_sandbox_config(sys.platform, args, execution_cwd)

            if args.run and prompt_sandbox_config.get("enabled") and prompt_sandbox_config.get("type") == "bubblewrap":
                if not check_bwrap_available():
                    raise RuntimeError(BWRAP_MISSING_ERROR)

            if not args.info_only:
                preview_command = cli_info["command"]
                if cli_info.get("stdin_mode") == "dash":
                    preview_command = preview_command + ["-"]
                prompt_info["cli_command"] = maybe_wrap_command_with_sandbox(preview_command, prompt_sandbox_config)
                prompt_info["cli_env"] = cli_info["env"]
                prompt_info["sandbox"] = prompt_sandbox_config

            if args.run:
                if args.loop:
                    # Verification loop mode
                    if args.loop_foreground:
                        # Run loop in foreground (called by background spawner or directly)
                        if prompt_sandbox_config.get("enabled"):
                            loop_result = run_verification_loop(
                                cli_info=cli_info,
                                original_content=prompt_info["content"],
                                cwd=execution_cwd,
                                log_dir=log_dir,
                                prompt_number=prompt_num,
                                model=args.model,
                                max_iterations=args.max_iterations,
                                completion_marker=args.completion_marker,
                                execution_timestamp=execution_timestamp,
                                sandbox_config=prompt_sandbox_config,
                                worktree_path=worktree_path,
                                branch_name=branch_name,
                                original_repo_root=original_repo_root,
                                require_diff=args.require_diff,
                            )
                        else:
                            loop_result = run_verification_loop(
                                cli_info=cli_info,
                                original_content=prompt_info["content"],
                                cwd=execution_cwd,
                                log_dir=log_dir,
                                prompt_number=prompt_num,
                                model=args.model,
                                max_iterations=args.max_iterations,
                                completion_marker=args.completion_marker,
                                execution_timestamp=execution_timestamp,
                                worktree_path=worktree_path,
                                branch_name=branch_name,
                                original_repo_root=original_repo_root,
                                require_diff=args.require_diff,
                            )
                        # For loop mode, show the loop log (exists immediately and is used by monitors)
                        prompt_info["log"] = loop_result["loop_log"]
                        prompt_info["execution"] = loop_result
                        raise_on_execution_error(loop_result, prompt_sandbox_config)
                    else:
                        # Start loop in background
                        loop_result = run_verification_loop_background(
                            cli_info=cli_info,
                            original_content=prompt_info["content"],
                            cwd=execution_cwd,
                            log_dir=log_dir,
                            prompt_number=prompt_num,
                            model=args.model,
                            max_iterations=args.max_iterations,
                            completion_marker=args.completion_marker,
                            execution_timestamp=execution_timestamp,
                            worktree_path=worktree_path,
                            branch_name=branch_name,
                            cli_override=args.cli,
                            variant=args.variant,
                            sandbox_enabled=bool(args.sandbox and not args.no_sandbox),
                            sandbox_type=args.sandbox_type,
                            sandbox_profile=args.sandbox_profile,
                            sandbox_workspace=args.sandbox_workspace,
                            sandbox_net=args.sandbox_net,
                            original_repo_root=original_repo_root,
                            require_diff=args.require_diff,
                        )
                        # For background loop, update displayed log to loop log
                        prompt_info["log"] = loop_result["loop_log"]
                        prompt_info["execution"] = loop_result
                        raise_on_execution_error(loop_result, prompt_sandbox_config)
                else:
                    # Standard single-run mode
                    if not cli_info["command"]:
                        # Claude subagent mode: create log file for metadata tracking
                        with open(log_file, "w") as f:
                            f.write(f"# Claude Subagent Execution\n")
                            f.write(f"# Prompt: {prompt_file.name}\n")
                            f.write(f"# Number: {prompt_num}\n")
                            f.write(f"# Started: {execution_timestamp}\n")
                            f.write(f"# CWD: {execution_cwd}\n")
                            f.write(f"# Worktree: {worktree_path}\n")
                            f.write(f"# Branch: {branch_name}\n")
                            f.write(f"\n")
                            f.write(f"# Prompt Content:\n")
                            f.write(f"# {'='*60}\n")
                            for line in prompt_info["content"].split('\n'):
                                f.write(f"# {line}\n")
                        exec_result = {"status": "subagent_required", "log": str(log_file)}
                    else:
                        if prompt_sandbox_config.get("enabled"):
                            exec_result = run_cli(
                                cli_info,
                                prompt_info["content"],
                                execution_cwd,
                                log_file,
                                sandbox_config=prompt_sandbox_config,
                            )
                        else:
                            exec_result = run_cli(
                                cli_info,
                                prompt_info["content"],
                                execution_cwd,
                                log_file,
                            )
                    prompt_info["execution"] = exec_result
                    raise_on_execution_error(exec_result, prompt_sandbox_config)

            result["prompts"].append(prompt_info)

        print(json.dumps(result, indent=2))

    except Exception as e:
        print(json.dumps({"error": str(e)}))
        sys.exit(1)



if __name__ == "__main__":
    main()
