#!/usr/bin/env python3
"""
Daplug config reader and migrator.

Reads settings from <daplug_config> blocks in CLAUDE.md, with legacy
plaintext fallback for backwards compatibility.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

CONFIG_OPEN = "<daplug_config>"
CONFIG_CLOSE = "</daplug_config>"

KNOWN_KEYS = [
    "preferred_agent",
    "worktree_dir",
    "llms_txt_dir",
    "ai_usage_awareness",
    "cli_logs_dir",
]

LEGACY_KEY_SET = set(KNOWN_KEYS)

BLOCK_LINE_RE = re.compile(r"^\s*([A-Za-z0-9_.-]+)\s*:\s*(.*?)\s*$")


def _agent_cache_path() -> Path:
    return Path.home() / ".claude" / "daplug-agents.json"


def _normalize_preferred_agent(value: str) -> str:
    v = (value or "").strip().lower()
    if v in {"claude-code", "claude_code"}:
        return "claude"
    if v.startswith("codex"):
        return "codex"
    if v.startswith("gemini"):
        return "gemini"
    if v in {"qwen", "devstral", "local"}:
        return "codex"
    return v


def _load_agent_cache() -> Optional[dict]:
    path = _agent_cache_path()
    if not path.exists():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except (OSError, json.JSONDecodeError):
        return None
    return raw if isinstance(raw, dict) else None


@dataclass
class FileConfig:
    path: Path
    data: Dict[str, str]
    format: str  # "block", "legacy", or "none"
    legacy_keys: List[str]
    has_block: bool
    malformed_block: bool
    warnings: List[str]


def _git_repo_root(start: Path) -> Path:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            check=True,
            cwd=start,
        )
        root = result.stdout.strip()
        return Path(root) if root else start
    except (subprocess.CalledProcessError, FileNotFoundError):
        return start


def _strip_inline_comment(value: str) -> str:
    # Strip inline comments only when preceded by whitespace.
    parts = re.split(r"\s+#", value, maxsplit=1)
    return parts[0].rstrip()


def _extract_blocks(content: str) -> Tuple[List[str], List[Tuple[int, int]], bool]:
    blocks: List[str] = []
    spans: List[Tuple[int, int]] = []
    malformed = False
    idx = 0
    while True:
        start = content.find(CONFIG_OPEN, idx)
        if start == -1:
            break
        end = content.find(CONFIG_CLOSE, start)
        if end == -1:
            # Treat remainder as malformed block.
            malformed = True
            block_body = content[start + len(CONFIG_OPEN) :]
            blocks.append(block_body)
            spans.append((start, len(content)))
            break
        block_body = content[start + len(CONFIG_OPEN) : end]
        blocks.append(block_body)
        spans.append((start, end + len(CONFIG_CLOSE)))
        idx = end + len(CONFIG_CLOSE)
    return blocks, spans, malformed


def _parse_block_lines(lines: Iterable[str]) -> Dict[str, str]:
    data: Dict[str, str] = {}
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        match = BLOCK_LINE_RE.match(stripped)
        if not match:
            continue
        key = match.group(1).strip()
        value = _strip_inline_comment(match.group(2).strip())
        data[key] = value
    return data


def _parse_blocks(content: str) -> Tuple[Dict[str, str], bool, bool]:
    blocks, _spans, malformed = _extract_blocks(content)
    if not blocks:
        return {}, False, False
    combined: Dict[str, str] = {}
    for block in blocks:
        block_data = _parse_block_lines(block.splitlines())
        combined.update(block_data)
    return combined, True, malformed


def _remove_spans(content: str, spans: List[Tuple[int, int]]) -> str:
    if not spans:
        return content
    new_content = []
    last_idx = 0
    for start, end in spans:
        new_content.append(content[last_idx:start])
        last_idx = end
    new_content.append(content[last_idx:])
    return "".join(new_content)


def _extract_legacy(content: str) -> Tuple[Dict[str, str], List[str]]:
    data: Dict[str, str] = {}
    legacy_keys: List[str] = []
    for line in content.splitlines():
        match = BLOCK_LINE_RE.match(line.strip())
        if not match:
            continue
        key = match.group(1).strip()
        if key not in LEGACY_KEY_SET:
            continue
        value = _strip_inline_comment(match.group(2).strip())
        data[key] = value
        legacy_keys.append(key)
    return data, sorted(set(legacy_keys))


def parse_config_content(content: str, path: Optional[Path] = None) -> FileConfig:
    path = path or Path("<memory>")
    block_data, has_block, malformed = _parse_blocks(content)
    warnings: List[str] = []

    spans: List[Tuple[int, int]] = []
    if has_block:
        _blocks, spans, _malformed = _extract_blocks(content)
        if malformed:
            warnings.append("Malformed <daplug_config> block (missing closing tag)")

    content_wo_blocks = _remove_spans(content, spans)
    legacy_data, legacy_keys = _extract_legacy(content_wo_blocks)

    if has_block:
        return FileConfig(
            path=path,
            data=block_data,
            format="block",
            legacy_keys=legacy_keys,
            has_block=True,
            malformed_block=malformed,
            warnings=warnings,
        )
    if legacy_data:
        warnings.append("Using legacy plaintext settings")
        return FileConfig(
            path=path,
            data=legacy_data,
            format="legacy",
            legacy_keys=legacy_keys,
            has_block=False,
            malformed_block=False,
            warnings=warnings,
        )
    return FileConfig(
        path=path,
        data={},
        format="none",
        legacy_keys=legacy_keys,
        has_block=False,
        malformed_block=False,
        warnings=warnings,
    )


def load_file_config(path: Path) -> FileConfig:
    if not path.exists():
        return FileConfig(
            path=path,
            data={},
            format="none",
            legacy_keys=[],
            has_block=False,
            malformed_block=False,
            warnings=[],
        )
    try:
        content = path.read_text()
    except OSError as exc:
        return FileConfig(
            path=path,
            data={},
            format="none",
            legacy_keys=[],
            has_block=False,
            malformed_block=False,
            warnings=[f"Failed to read {path}: {exc}"]
        )
    return parse_config_content(content, path=path)


def merge_configs(project: FileConfig, user: FileConfig) -> Dict[str, str]:
    merged = dict(user.data)
    merged.update(project.data)
    return merged


def resolve_setting(
    key: str,
    project: FileConfig,
    user: FileConfig,
) -> Tuple[Optional[str], str]:
    if key in project.data:
        return project.data[key], "project"
    if key in user.data:
        return user.data[key], "user"
    return None, "none"


def format_block(data: Dict[str, str]) -> str:
    ordered: List[str] = []
    for key in KNOWN_KEYS:
        if key in data:
            ordered.append(key)
    extras = sorted(k for k in data.keys() if k not in ordered)
    ordered.extend(extras)
    lines = [CONFIG_OPEN]
    for key in ordered:
        value = data[key]
        lines.append(f"{key}: {value}")
    lines.append(CONFIG_CLOSE)
    return "\n".join(lines)


def insert_block(content: str, block_text: str) -> str:
    if not content.strip():
        return block_text + "\n"
    lines = content.splitlines(keepends=True)
    for idx, line in enumerate(lines):
        if line.strip() == "## daplug Settings":
            insert_at = idx + 1
            prefix = "".join(lines[:insert_at])
            suffix = "".join(lines[insert_at:])
            separator = "" if prefix.endswith("\n") else "\n"
            block = block_text + "\n"
            return prefix + separator + block + suffix
    separator = "" if content.endswith("\n") else "\n"
    return content + separator + "\n" + block_text + "\n"


def remove_legacy_lines(content: str) -> str:
    lines = content.splitlines(keepends=True)
    cleaned: List[str] = []
    for line in lines:
        match = BLOCK_LINE_RE.match(line.strip())
        if match and match.group(1).strip() in LEGACY_KEY_SET:
            continue
        cleaned.append(line)
    return "".join(cleaned)


def migrate_content(content: str) -> Tuple[str, bool, Dict[str, str]]:
    block_data, has_block, malformed = _parse_blocks(content)
    blocks, spans, _malformed = _extract_blocks(content)
    content_wo_blocks = _remove_spans(content, spans)
    legacy_data, legacy_keys = _extract_legacy(content_wo_blocks)

    if not legacy_keys and has_block and not malformed:
        return content, False, block_data
    if not legacy_keys and not has_block:
        return content, False, {}

    merged = dict(block_data)
    for key, value in legacy_data.items():
        if key not in merged or merged[key] == "":
            merged[key] = value

    cleaned = remove_legacy_lines(content_wo_blocks)
    new_block = format_block(merged)
    new_content = insert_block(cleaned.rstrip() + "\n", new_block)
    return new_content, True, merged


def set_content_value(content: str, key: str, value: str) -> Tuple[str, Dict[str, str]]:
    block_data, _has_block, _malformed = _parse_blocks(content)
    blocks, spans, _malformed = _extract_blocks(content)
    content_wo_blocks = _remove_spans(content, spans)
    legacy_data, _legacy_keys = _extract_legacy(content_wo_blocks)

    merged = dict(block_data) if block_data else dict(legacy_data)
    merged[key] = value

    cleaned = remove_legacy_lines(content_wo_blocks)
    new_block = format_block(merged)
    new_content = insert_block(cleaned.rstrip() + "\n", new_block)
    return new_content, merged


def write_with_backup(path: Path, content: str) -> Optional[Path]:
    if path.exists():
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        backup_path = Path(f"{path}.bak-{timestamp}")
        backup_path.write_text(path.read_text())
    else:
        backup_path = None
        path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    return backup_path


def warn(messages: Iterable[str], quiet: bool) -> None:
    if quiet:
        return
    for message in messages:
        print(f"WARNING: {message}", file=sys.stderr)


def get_paths(repo_root: Optional[str], project_path: Optional[str], user_path: Optional[str]) -> Tuple[Path, Path]:
    if project_path:
        project = Path(project_path)
    else:
        start = Path(repo_root) if repo_root else Path.cwd()
        project = _git_repo_root(start) / "CLAUDE.md"
    if user_path:
        user = Path(user_path)
    else:
        user = Path.home() / ".claude" / "CLAUDE.md"
    return project, user


def cmd_get(args: argparse.Namespace) -> int:
    project_path, user_path = get_paths(args.repo_root, args.project_path, args.user_path)
    project = load_file_config(project_path)
    user = load_file_config(user_path)
    value, source = resolve_setting(args.key, project, user)
    warnings = []
    if project.format == "legacy" or user.format == "legacy":
        warnings.append("Using legacy plaintext settings; run /daplug:migrate-config")
    warn(project.warnings + user.warnings + warnings, args.quiet)
    if value is None:
        return 0
    print(value)
    return 0


def cmd_dump(args: argparse.Namespace) -> int:
    project_path, user_path = get_paths(args.repo_root, args.project_path, args.user_path)
    project = load_file_config(project_path)
    user = load_file_config(user_path)
    merged = merge_configs(project, user)
    warnings = []
    if project.format == "legacy" or user.format == "legacy":
        warnings.append("Using legacy plaintext settings; run /daplug:migrate-config")
    warn(project.warnings + user.warnings + warnings, args.quiet)

    if args.env:
        for key, value in merged.items():
            env_key = re.sub(r"[^A-Za-z0-9]", "_", key).upper()
            print(f"{env_key}={value}")
        return 0

    print(json.dumps(merged))
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    project_path, user_path = get_paths(args.repo_root, args.project_path, args.user_path)
    project = load_file_config(project_path)
    user = load_file_config(user_path)
    merged = merge_configs(project, user)
    legacy = {
        "project": project.legacy_keys,
        "user": user.legacy_keys,
    }
    needs_migration = bool(project.legacy_keys or user.legacy_keys)

    agent_cache = _load_agent_cache()
    cache_path = _agent_cache_path()
    preferred_raw = str(merged.get("preferred_agent") or "").strip()
    preferred_norm = _normalize_preferred_agent(preferred_raw) if preferred_raw else ""
    preferred_info: Optional[dict] = None
    if preferred_raw:
        clis = (agent_cache or {}).get("clis") if isinstance(agent_cache, dict) else None
        entry = clis.get(preferred_norm) if isinstance(clis, dict) else None
        installed = bool(entry.get("installed")) if isinstance(entry, dict) else None
        preferred_info = {
            "value": preferred_raw,
            "normalized": preferred_norm,
            "known": isinstance(clis, dict) and preferred_norm in clis,
            "installed": installed,
        }

    status = {
        "paths": {
            "project": str(project_path),
            "user": str(user_path),
        },
        "settings": {
            key: {"value": value, "source": resolve_setting(key, project, user)[1]}
            for key, value in merged.items()
        },
        "needs_migration": needs_migration,
        "legacy_settings": sorted(set(project.legacy_keys + user.legacy_keys)),
        "legacy_files": legacy,
        "agent_cache": {
            "path": str(cache_path),
            "exists": agent_cache is not None,
            "preferred_agent": preferred_info,
        },
    }

    if args.json:
        print(json.dumps(status))
        return 0

    print("Config status:")
    print(f"- Project CLAUDE.md: {project_path}")
    print(f"- User CLAUDE.md: {user_path}")
    if merged:
        print("\nSettings:")
        for key, info in status["settings"].items():
            print(f"- {key}: {info['value']} ({info['source']})")
    else:
        print("\nSettings: none")
    if needs_migration:
        print("\nLegacy settings detected:")
        for scope, keys in legacy.items():
            if keys:
                print(f"- {scope}: {', '.join(keys)}")
        print("Run /daplug:migrate-config to upgrade.")
    if preferred_raw:
        if agent_cache is None:
            print(
                f"\nCLI cache not found ({cache_path}). Run /daplug:detect-clis to validate preferred_agent."
            )
        elif preferred_info and preferred_info.get("known") is False:
            print(
                f"\n⚠️ preferred_agent '{preferred_raw}' is not a known CLI in the CLI cache. Run /daplug:detect-clis."
            )
        elif preferred_info and preferred_info.get("installed") is False:
            print(
                f"\n⚠️ preferred_agent '{preferred_raw}' is not installed (per {cache_path}). Run /daplug:detect-clis."
            )
    return 0


def cmd_check_legacy(args: argparse.Namespace) -> int:
    project_path, user_path = get_paths(args.repo_root, args.project_path, args.user_path)
    project = load_file_config(project_path)
    user = load_file_config(user_path)
    legacy_settings = sorted(set(project.legacy_keys + user.legacy_keys))
    result = {
        "needs_migration": bool(legacy_settings),
        "legacy_settings": legacy_settings,
        "legacy_files": {
            "project": project.legacy_keys,
            "user": user.legacy_keys,
        },
        "paths": {
            "project": str(project_path),
            "user": str(user_path),
        },
    }
    print(json.dumps(result))
    return 0


def cmd_migrate(args: argparse.Namespace) -> int:
    project_path, user_path = get_paths(args.repo_root, args.project_path, args.user_path)

    scopes: List[Tuple[str, Path]] = []
    if args.project or args.all:
        scopes.append(("project", project_path))
    if args.user or args.all:
        scopes.append(("user", user_path))
    if not scopes:
        scopes = [("project", project_path), ("user", user_path)]

    changed_any = False
    results = {}
    for scope, path in scopes:
        if not path.exists():
            results[scope] = {"path": str(path), "changed": False, "reason": "missing"}
            continue
        content = path.read_text()
        new_content, changed, merged = migrate_content(content)
        if changed and not args.dry_run:
            backup = write_with_backup(path, new_content)
            results[scope] = {
                "path": str(path),
                "changed": True,
                "backup": str(backup) if backup else None,
                "settings": merged,
            }
            changed_any = True
        else:
            results[scope] = {
                "path": str(path),
                "changed": False,
                "settings": merged,
            }
    print(json.dumps({"changed": changed_any, "results": results}))
    return 0


def cmd_set(args: argparse.Namespace) -> int:
    project_path, user_path = get_paths(args.repo_root, args.project_path, args.user_path)
    if args.scope == "project":
        target = project_path
    else:
        target = user_path

    content = target.read_text() if target.exists() else ""
    new_content, merged = set_content_value(content, args.key, args.value)
    backup = write_with_backup(target, new_content)
    output = {
        "path": str(target),
        "backup": str(backup) if backup else None,
        "settings": merged,
    }
    print(json.dumps(output))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Read daplug config from CLAUDE.md")
    parser.add_argument("--repo-root", help="Override repo root for project CLAUDE.md")
    parser.add_argument("--project-path", help="Override project CLAUDE.md path")
    parser.add_argument("--user-path", help="Override user CLAUDE.md path")
    parser.add_argument("--quiet", action="store_true", help="Suppress warnings")

    subparsers = parser.add_subparsers(dest="command", required=True)

    get_parser = subparsers.add_parser("get", help="Get a single setting")
    get_parser.add_argument("key")
    get_parser.set_defaults(func=cmd_get)

    dump_parser = subparsers.add_parser("dump", help="Dump all settings")
    dump_parser.add_argument("--json", action="store_true", help="Output JSON")
    dump_parser.add_argument("--env", action="store_true", help="Output as ENV var lines")
    dump_parser.set_defaults(func=cmd_dump)

    status_parser = subparsers.add_parser("status", help="Show config status")
    status_parser.add_argument("--json", action="store_true")
    status_parser.set_defaults(func=cmd_status)

    legacy_parser = subparsers.add_parser("check-legacy", help="Check for legacy settings")
    legacy_parser.set_defaults(func=cmd_check_legacy)

    migrate_parser = subparsers.add_parser("migrate", help="Migrate legacy settings to XML block")
    migrate_parser.add_argument("--project", action="store_true", help="Migrate project CLAUDE.md")
    migrate_parser.add_argument("--user", action="store_true", help="Migrate user CLAUDE.md")
    migrate_parser.add_argument("--all", action="store_true", help="Migrate both project and user")
    migrate_parser.add_argument("--dry-run", action="store_true", help="Show changes without writing")
    migrate_parser.set_defaults(func=cmd_migrate)

    set_parser = subparsers.add_parser("set", help="Set a setting in CLAUDE.md")
    set_parser.add_argument("key")
    set_parser.add_argument("value")
    set_parser.add_argument("--scope", choices=["project", "user"], required=True)
    set_parser.set_defaults(func=cmd_set)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
