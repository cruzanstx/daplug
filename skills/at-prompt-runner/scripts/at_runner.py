#!/usr/bin/env python3
"""
Agent-team prompt runner helper.

Supports:
- Parsing orchestration group syntax
- Prompt existence validation through prompt-manager
- Heuristic auto-dependency planning
- Execution plan generation for /run-prompt delegation
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

PromptRef = int | str

PROMPT_TOKEN_RE = re.compile(
    r"^(?:(?P<folder>[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)*)/)?(?P<number>\d+)$"
)

DEPENDENCY_LINE_RE = re.compile(
    r"^\s*(?:depends_on|depends-on|dependencies?|requires?)\s*:\s*(?P<value>.+)$",
    re.IGNORECASE | re.MULTILINE,
)
PHRASE_DEP_RE = re.compile(
    r"(?:depends on|after|blocked by|requires)\s+(?P<value>[A-Za-z0-9_./,\s-]+)",
    re.IGNORECASE,
)


@dataclass
class ScriptPaths:
    plugin_root: Path
    prompt_manager: Path
    config_reader: Path | None


def _installed_plugin_root() -> Path | None:
    manifest = Path.home() / ".claude" / "plugins" / "installed_plugins.json"
    if not manifest.exists():
        return None
    try:
        data = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    try:
        install_path = data["plugins"]["daplug@cruzanstx"][0]["installPath"]
    except (KeyError, IndexError, TypeError):
        return None
    if not isinstance(install_path, str) or not install_path.strip():
        return None
    return Path(install_path).expanduser()


def _dedupe_paths(paths: list[Path]) -> list[Path]:
    seen: set[str] = set()
    out: list[Path] = []
    for p in paths:
        key = str(p.resolve()) if p.exists() else str(p)
        if key in seen:
            continue
        seen.add(key)
        out.append(p)
    return out


def _candidate_plugin_roots() -> list[Path]:
    candidates: list[Path] = []
    env_root = os.environ.get("PLUGIN_ROOT")
    if env_root:
        candidates.append(Path(env_root).expanduser())

    # If this script is inside a plugin-like tree, this resolves to that root.
    candidates.append(Path(__file__).resolve().parents[3])

    installed = _installed_plugin_root()
    if installed:
        candidates.append(installed)

    return _dedupe_paths(candidates)


def resolve_script_paths() -> ScriptPaths:
    manager_rel = Path("skills/prompt-manager/scripts/manager.py")
    config_rel = Path("skills/config-reader/scripts/config.py")

    manager_path: Path | None = None
    config_path: Path | None = None
    chosen_root: Path | None = None

    for root in _candidate_plugin_roots():
        candidate_manager = root / manager_rel
        if candidate_manager.exists():
            manager_path = candidate_manager
            config_candidate = root / config_rel
            config_path = config_candidate if config_candidate.exists() else None
            chosen_root = root
            break

    if manager_path is None:
        raise RuntimeError(
            "Could not locate prompt-manager script. "
            "Set PLUGIN_ROOT or install daplug plugin."
        )

    assert chosen_root is not None
    return ScriptPaths(
        plugin_root=chosen_root,
        prompt_manager=manager_path,
        config_reader=config_path,
    )


def get_repo_root() -> Path:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            check=True,
        )
        return Path(result.stdout.strip())
    except (subprocess.CalledProcessError, FileNotFoundError):
        return Path.cwd()


def _prompt_ref_key(ref: PromptRef) -> str:
    return str(ref)


def prompt_ref_to_query(ref: PromptRef) -> str:
    if isinstance(ref, int):
        return str(ref)
    return ref


def normalize_prompt_token(token: str) -> PromptRef:
    raw = token.strip()
    if not raw:
        raise ValueError("Empty prompt token")

    match = PROMPT_TOKEN_RE.match(raw)
    if not match:
        raise ValueError(f"Invalid prompt token: {token}")

    folder = match.group("folder")
    number = int(match.group("number"))
    if folder:
        return f"{folder}/{number:03d}"
    return number


def _tokenize_phase(segment: str) -> list[str]:
    return [token for token in re.split(r"[\s,]+", segment.strip()) if token]


def parse_group_syntax(input_str: str) -> list[dict[str, Any]]:
    text = input_str.strip()
    if not text:
        raise ValueError("Group syntax cannot be empty")

    segments = [segment.strip() for segment in text.split("->")]
    if any(not segment for segment in segments):
        raise ValueError("Invalid group syntax: empty phase found around '->'")

    phases: list[dict[str, Any]] = []
    for phase_index, segment in enumerate(segments, start=1):
        tokens = _tokenize_phase(segment)
        if not tokens:
            raise ValueError(f"Phase {phase_index} does not contain any prompts")

        prompts: list[PromptRef] = []
        seen: set[str] = set()
        for token in tokens:
            ref = normalize_prompt_token(token)
            key = _prompt_ref_key(ref)
            if key in seen:
                continue
            seen.add(key)
            prompts.append(ref)

        phases.append(
            {
                "phase": phase_index,
                "prompts": prompts,
                "strategy": "parallel",
            }
        )

    return phases


def parse_prompt_list(input_str: str) -> list[PromptRef]:
    raw = input_str.replace("->", " ")
    tokens = [token for token in re.split(r"[\s,]+", raw.strip()) if token]
    if not tokens:
        raise ValueError("No prompts found in input")

    refs: list[PromptRef] = []
    seen: set[str] = set()
    for token in tokens:
        ref = normalize_prompt_token(token)
        key = _prompt_ref_key(ref)
        if key in seen:
            continue
        seen.add(key)
        refs.append(ref)
    return refs


def _run_script(path: Path, args: list[str]) -> subprocess.CompletedProcess[str]:
    cmd = [sys.executable, str(path), *args]
    return subprocess.run(cmd, capture_output=True, text=True, check=False)


def _prompt_manager_find(paths: ScriptPaths, ref: PromptRef) -> dict[str, Any] | None:
    result = _run_script(paths.prompt_manager, ["find", prompt_ref_to_query(ref), "--json"])
    if result.returncode != 0:
        return None
    try:
        parsed = json.loads(result.stdout)
    except json.JSONDecodeError:
        return None
    if isinstance(parsed, dict):
        return parsed
    return None


def _prompt_manager_read(paths: ScriptPaths, ref: PromptRef) -> str:
    result = _run_script(paths.prompt_manager, ["read", prompt_ref_to_query(ref)])
    if result.returncode != 0:
        stderr = result.stderr.strip() or "unknown error"
        raise RuntimeError(
            f"Failed to read prompt {prompt_ref_to_query(ref)} via prompt-manager: {stderr}"
        )
    return result.stdout


def _extract_number_from_ref(ref: PromptRef) -> int:
    if isinstance(ref, int):
        return ref
    return int(ref.rsplit("/", 1)[-1])


def _extract_dependency_refs(text: str, allowed_refs: list[PromptRef], current: PromptRef) -> set[str]:
    allowed_by_number = {str(_extract_number_from_ref(ref)): _prompt_ref_key(ref) for ref in allowed_refs}
    dependencies: set[str] = set()

    def _collect_tokens(value: str) -> None:
        for token in re.split(r"[\s,]+", value.strip()):
            if not token:
                continue
            try:
                ref = normalize_prompt_token(token)
            except ValueError:
                continue
            key = _prompt_ref_key(ref)
            if key != _prompt_ref_key(current):
                dependencies.add(key)

    for match in DEPENDENCY_LINE_RE.finditer(text):
        _collect_tokens(match.group("value"))

    for match in PHRASE_DEP_RE.finditer(text):
        _collect_tokens(match.group("value"))

    lowered = text.lower()
    for number, ref_key in allowed_by_number.items():
        if ref_key == _prompt_ref_key(current):
            continue
        patterns = [
            rf"\bprompt\s*#?\s*0*{re.escape(number)}\b",
            rf"\b0*{re.escape(number)}\s*-\s*[a-z0-9]",
        ]
        if any(re.search(pattern, lowered) for pattern in patterns):
            dependencies.add(ref_key)

    return dependencies


def _classify_prompt(text: str) -> str:
    lowered = text.lower()
    validation_keywords = (
        "test",
        "validate",
        "verification",
        "lint",
        "qa",
        "assert",
        "check",
    )
    setup_keywords = (
        "setup",
        "bootstrap",
        "schema",
        "migration",
        "foundation",
        "initialize",
        "init ",
    )

    if any(keyword in lowered for keyword in validation_keywords):
        return "validation"
    if any(keyword in lowered for keyword in setup_keywords):
        return "setup"
    return "implementation"


def _topological_phases(
    refs: list[PromptRef], deps: dict[str, set[str]]
) -> tuple[list[list[PromptRef]], list[PromptRef]]:
    order_keys = [_prompt_ref_key(ref) for ref in refs]
    key_to_ref = {_prompt_ref_key(ref): ref for ref in refs}

    remaining: set[str] = set(order_keys)
    incoming: dict[str, set[str]] = {
        key: {dep for dep in deps.get(key, set()) if dep in remaining}
        for key in order_keys
    }
    phases: list[list[PromptRef]] = []

    while remaining:
        ready_keys = [
            key for key in order_keys if key in remaining and not incoming.get(key, set())
        ]
        if not ready_keys:
            cycle = [key_to_ref[key] for key in order_keys if key in remaining]
            return phases, cycle

        phase = [key_to_ref[key] for key in ready_keys]
        phases.append(phase)

        for key in ready_keys:
            remaining.discard(key)

        for key in remaining:
            incoming[key] = incoming[key] - set(ready_keys)

    return phases, []


def infer_auto_dependencies(
    prompt_refs: list[PromptRef], paths: ScriptPaths
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if not prompt_refs:
        raise ValueError("No prompts supplied for --auto-deps")

    content_map: dict[str, str] = {}
    classifications: dict[str, str] = {}
    read_errors: list[dict[str, str]] = []
    for ref in prompt_refs:
        key = _prompt_ref_key(ref)
        try:
            content = _prompt_manager_read(paths, ref)
        except RuntimeError as exc:
            # Keep auto-deps usable for planning even when some prompts do not exist
            # yet; validation step is the hard gate for existence checks.
            content = ""
            read_errors.append({"prompt": prompt_ref_to_query(ref), "error": str(exc)})
        content_map[key] = content
        classifications[key] = _classify_prompt(content)

    deps: dict[str, set[str]] = {}
    for ref in prompt_refs:
        key = _prompt_ref_key(ref)
        deps[key] = _extract_dependency_refs(content_map[key], prompt_refs, ref)

    # Heuristic fallback: validation prompts should run after non-validation prompts.
    if all(len(values) == 0 for values in deps.values()):
        validation = [key for key, cls in classifications.items() if cls == "validation"]
        non_validation = [key for key in classifications if key not in validation]
        if validation and non_validation:
            for key in validation:
                deps[key] = set(non_validation)

    # Heuristic fallback: setup prompts should run before implementation prompts.
    if all(len(values) == 0 for values in deps.values()):
        setup = [key for key, cls in classifications.items() if cls == "setup"]
        non_setup = [key for key in classifications if key not in setup]
        if setup and non_setup:
            for key in non_setup:
                deps[key] = set(setup)

    raw_phases, cycle = _topological_phases(prompt_refs, deps)
    if cycle:
        # Fall back to explicit sequential phases when a cycle is detected.
        raw_phases = [[ref] for ref in prompt_refs]

    phases: list[dict[str, Any]] = []
    for idx, phase_prompts in enumerate(raw_phases, start=1):
        phases.append(
            {
                "phase": idx,
                "prompts": phase_prompts,
                "strategy": "parallel",
            }
        )

    metadata = {
        "dependency_graph": {
            key: sorted(values, key=str) for key, values in deps.items()
        },
        "classifications": classifications,
        "read_errors": read_errors,
        "cycle_detected": bool(cycle),
        "cycle_prompts": cycle,
    }
    return phases, metadata


def collect_prompt_refs(phases: list[dict[str, Any]]) -> list[PromptRef]:
    refs: list[PromptRef] = []
    seen: set[str] = set()
    for phase in phases:
        for ref in phase.get("prompts", []):
            key = _prompt_ref_key(ref)
            if key in seen:
                continue
            seen.add(key)
            refs.append(ref)
    return refs


def validate_prompts(phases: list[dict[str, Any]], paths: ScriptPaths) -> dict[str, Any]:
    refs = collect_prompt_refs(phases)
    found: list[dict[str, Any]] = []
    missing: list[dict[str, Any]] = []

    for ref in refs:
        info = _prompt_manager_find(paths, ref)
        query = prompt_ref_to_query(ref)
        if info is None:
            missing.append({"prompt": ref, "query": query})
            continue
        found.append(
            {
                "prompt": ref,
                "query": query,
                "path": info.get("path"),
                "status": info.get("status"),
                "folder": info.get("folder", ""),
                "name": info.get("name"),
            }
        )

    return {
        "ok": len(missing) == 0,
        "found": found,
        "missing": missing,
        "total": len(refs),
    }


def _format_flag_parts(flags: dict[str, Any]) -> list[str]:
    parts: list[str] = []
    if flags.get("worktree"):
        parts.append("--worktree")
    if flags.get("loop"):
        parts.append("--loop")
    return parts


def _build_run_prompt_command(prompt_ref: PromptRef, model: str, flags: dict[str, Any]) -> str:
    parts = ["/run-prompt", prompt_ref_to_query(prompt_ref), "--model", model]
    parts.extend(_format_flag_parts(flags))
    return " ".join(parts)


def format_run_commands(plan: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for phase in plan.get("phases", []):
        commands = [
            command.get("command")
            for command in phase.get("commands", [])
            if isinstance(command, dict) and command.get("command")
        ]
        out.append(
            {
                "phase": phase.get("phase"),
                "strategy": phase.get("strategy", "parallel"),
                "commands": commands,
            }
        )
    return out


def build_execution_plan(
    phases: list[dict[str, Any]],
    model: str,
    flags: dict[str, Any],
) -> dict[str, Any]:
    plan: dict[str, Any] = {
        "model": model,
        "flags": flags,
        "total_phases": len(phases),
        "total_prompts": sum(len(phase.get("prompts", [])) for phase in phases),
        "phases": [],
    }

    for phase in phases:
        prompt_refs = phase.get("prompts", [])
        commands = [
            {
                "prompt": prompt_ref,
                "command": _build_run_prompt_command(prompt_ref, model, flags),
            }
            for prompt_ref in prompt_refs
        ]
        plan["phases"].append(
            {
                "phase": phase.get("phase"),
                "strategy": phase.get("strategy", "parallel"),
                "prompts": prompt_refs,
                "commands": commands,
            }
        )

    plan["run_commands"] = format_run_commands(plan)
    if flags.get("validate"):
        plan["post_phase"] = "at-validator"
    return plan


def _human_plan(plan: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append("Execution plan:")
    lines.append(f"- Model: {plan.get('model')}")
    lines.append(f"- Total phases: {plan.get('total_phases')}")
    lines.append(f"- Total prompts: {plan.get('total_prompts')}")
    lines.append(
        f"- Dry run: {'yes' if plan.get('flags', {}).get('dry_run') else 'no'}"
    )
    flag_parts = _format_flag_parts(plan.get("flags", {}))
    lines.append(f"- /run-prompt flags: {' '.join(flag_parts) if flag_parts else '(none)'}")
    if plan.get("flags", {}).get("validate"):
        lines.append("- Validation phase: enabled (at-validator)")
    lines.append("")

    for phase in plan.get("phases", []):
        lines.append(f"Phase {phase.get('phase')} [{phase.get('strategy', 'parallel')}]")
        for cmd in phase.get("commands", []):
            lines.append(f"  {cmd.get('command')}")
        lines.append("")

    return "\n".join(lines).rstrip()


def _read_preferred_model(paths: ScriptPaths, repo_root: Path) -> str | None:
    if paths.config_reader is None:
        return None
    result = _run_script(
        paths.config_reader,
        ["get", "preferred_agent", "--repo-root", str(repo_root), "--quiet"],
    )
    if result.returncode != 0:
        return None
    value = result.stdout.strip()
    return value or None


def _resolve_model(paths: ScriptPaths, requested_model: str | None) -> str:
    if requested_model:
        return requested_model
    preferred = _read_preferred_model(paths, get_repo_root())
    return preferred or "claude"


def _parse_input(
    input_str: str, auto_deps: bool, paths: ScriptPaths
) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    if not auto_deps:
        return parse_group_syntax(input_str), None

    refs = parse_prompt_list(input_str)
    phases, metadata = infer_auto_dependencies(refs, paths)
    return phases, metadata


def cmd_parse(args: argparse.Namespace, paths: ScriptPaths) -> int:
    phases, metadata = _parse_input(args.group_syntax, args.auto_deps, paths)

    if args.auto_deps and args.json:
        payload = {"phases": phases, "auto_deps": metadata}
    else:
        payload = phases
    print(json.dumps(payload, indent=2))
    return 0


def cmd_validate(args: argparse.Namespace, paths: ScriptPaths) -> int:
    phases, metadata = _parse_input(args.group_syntax, args.auto_deps, paths)
    validation = validate_prompts(phases, paths)

    if args.json:
        payload: dict[str, Any] = {
            "phases": phases,
            "validation": validation,
        }
        if metadata is not None:
            payload["auto_deps"] = metadata
        print(json.dumps(payload, indent=2))
    else:
        if validation["ok"]:
            print(f"Validation OK: {validation['total']} prompt(s) found.")
            for prompt in validation["found"]:
                print(f"- {prompt['query']}: {prompt.get('path')}")
        else:
            print(
                f"Validation failed: {len(validation['missing'])} of "
                f"{validation['total']} prompt(s) were not found.",
                file=sys.stderr,
            )
            for missing in validation["missing"]:
                print(f"- Missing: {missing['query']}", file=sys.stderr)

    return 0 if validation["ok"] else 1


def cmd_plan(args: argparse.Namespace, paths: ScriptPaths) -> int:
    phases, metadata = _parse_input(args.group_syntax, args.auto_deps, paths)
    validation = validate_prompts(phases, paths)

    model = _resolve_model(paths, args.model)
    flags = {
        "worktree": bool(args.worktree),
        "loop": bool(args.loop),
        "validate": bool(args.validate),
        "dry_run": bool(args.dry_run),
    }

    plan = build_execution_plan(phases, model, flags)
    payload: dict[str, Any] = {
        "plan": plan,
        "validation": validation,
    }
    if metadata is not None:
        payload["auto_deps"] = metadata

    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        print(_human_plan(plan))
        if not validation["ok"]:
            print("")
            print("Missing prompts:")
            for missing in validation["missing"]:
                print(f"- {missing['query']}")

    return 0 if validation["ok"] else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Parse and plan agent-team prompt orchestration groups"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    parse_parser = subparsers.add_parser("parse", help="Parse group syntax")
    parse_parser.add_argument("group_syntax", help='e.g. "220,221 -> 222,223 -> 224"')
    parse_parser.add_argument(
        "--auto-deps",
        action="store_true",
        help="Use heuristic dependency ordering from prompt contents",
    )
    parse_parser.add_argument(
        "--json",
        action="store_true",
        help="Include auto-deps metadata (when enabled)",
    )

    validate_parser = subparsers.add_parser(
        "validate", help="Validate that all referenced prompts exist"
    )
    validate_parser.add_argument("group_syntax", help="Group syntax or prompt list")
    validate_parser.add_argument(
        "--auto-deps",
        action="store_true",
        help="Apply heuristic auto-deps before validation",
    )
    validate_parser.add_argument("--json", action="store_true", help="Output JSON")

    plan_parser = subparsers.add_parser("plan", help="Build execution plan JSON")
    plan_parser.add_argument("group_syntax", help="Group syntax or prompt list")
    plan_parser.add_argument("--model", default=None, help="Default model for commands")
    plan_parser.add_argument(
        "--auto-deps",
        action="store_true",
        help="Infer phase order from prompt contents",
    )
    plan_parser.add_argument("--worktree", action="store_true", help="Add --worktree flag")
    plan_parser.add_argument("--loop", action="store_true", help="Add --loop flag")
    plan_parser.add_argument(
        "--validate",
        action="store_true",
        help="Append final validator phase in plan metadata",
    )
    plan_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Mark plan as dry-run (no execution side effects)",
    )
    plan_parser.add_argument("--json", action="store_true", help="Output JSON")

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    try:
        paths = resolve_script_paths()

        if args.command == "parse":
            return cmd_parse(args, paths)
        if args.command == "validate":
            return cmd_validate(args, paths)
        if args.command == "plan":
            return cmd_plan(args, paths)

        parser.print_help()
        return 1
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except RuntimeError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:  # pragma: no cover - defensive
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
