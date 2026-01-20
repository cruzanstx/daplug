#!/usr/bin/env python3
from __future__ import annotations

import argparse
import copy
import json
import re
import shutil
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from cache import AgentCache
from plugins.base import CLIPlugin, ConfigIssue

TEMPLATES_DIR = Path(__file__).resolve().parents[1] / "templates"

TEMPLATE_FILES: dict[str, str] = {
    "claude": "claude.json",
    "codex": "codex.json",
    "gemini": "gemini.json",
    "opencode": "opencode.json",
}

FIX_TEMPLATES: dict[str, dict[str, dict[str, Any]]] = {
    "codex": {
        "sandbox_permissions": {
            "permissions": {"*": "allow"},
        }
    },
    "opencode": {
        "sandbox_permissions": {
            "permission": {"*": "allow", "external_directory": "allow"},
        }
    },
}


@dataclass
class FixResult:
    cli: str
    issue_type: str
    config_path: str
    success: bool
    message: str
    backup_path: Optional[str] = None


def _strip_jsonc(text: str) -> str:
    text = re.sub(r"(?m)^\\s*//.*$", "", text)
    text = re.sub(r"(?m)^\\s*#.*$", "", text)
    text = re.sub(r"/\\*.*?\\*/", "", text, flags=re.DOTALL)
    return text


def _now_timestamp() -> str:
    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%f")
    return f"{ts}-{time.time_ns()}"


def deep_merge_defaults(target: dict[str, Any], defaults: dict[str, Any]) -> dict[str, Any]:
    """Merge defaults into target without overwriting user values."""
    result = copy.deepcopy(target)
    for key, value in defaults.items():
        if key not in result or result[key] is None:
            result[key] = copy.deepcopy(value)
            continue
        if isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = deep_merge_defaults(result[key], value)
    return result


def deep_merge_overwrite(target: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    """Merge patch into target, overwriting only keys present in patch."""
    result = copy.deepcopy(target)
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = deep_merge_overwrite(result[key], value)
            continue
        result[key] = copy.deepcopy(value)
    return result


def load_template(cli_name: str) -> dict[str, Any]:
    filename = TEMPLATE_FILES.get(cli_name)
    if not filename:
        return {}
    path = TEMPLATES_DIR / filename
    content = path.read_text(encoding="utf-8", errors="replace")
    if path.suffix.lower() in {".json", ".jsonc"}:
        return json.loads(_strip_jsonc(content))
    if path.suffix.lower() in {".yml", ".yaml"}:
        import yaml  # lazy import

        loaded = yaml.safe_load(content)  # type: ignore[no-untyped-call]
        return loaded if isinstance(loaded, dict) else {}
    return {}


def backup_config(path: Path) -> Path:
    """Create timestamped backup, return backup path."""
    if not path.exists():
        raise FileNotFoundError(str(path))

    ts = _now_timestamp()
    backup_path = Path(str(path) + f".bak.{ts}")
    backup_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, backup_path)

    # Keep last 3 backups per config.
    backups = sorted(
        path.parent.glob(path.name + ".bak.*"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    for old in backups[3:]:
        try:
            old.unlink()
        except OSError:
            pass

    return backup_path


def apply_fix_safely(plugin: CLIPlugin, issue: ConfigIssue) -> FixResult:
    """Apply fix with backup and rollback on failure."""
    config_path = Path(issue.config_path).expanduser() if issue.config_path else None
    if config_path is None:
        # Best-effort fallback to plugin's first config path.
        paths = plugin.get_config_paths()
        config_path = paths[0] if paths else Path(".")

    backup_path: Optional[Path] = None
    try:
        if config_path.exists():
            backup_path = backup_config(config_path)

        ok = plugin.apply_fix(issue)
        if not ok:
            if backup_path and config_path.exists():
                shutil.copy2(backup_path, config_path)
            return FixResult(
                cli=plugin.name,
                issue_type=issue.type,
                config_path=str(config_path),
                success=False,
                message="Fix failed",
                backup_path=str(backup_path) if backup_path else None,
            )

        remaining = [i for i in plugin.detect_issues() if i.type == issue.type]
        if remaining:
            if backup_path and config_path.exists():
                shutil.copy2(backup_path, config_path)
            return FixResult(
                cli=plugin.name,
                issue_type=issue.type,
                config_path=str(config_path),
                success=False,
                message="Fix applied but validation failed",
                backup_path=str(backup_path) if backup_path else None,
            )

        return FixResult(
            cli=plugin.name,
            issue_type=issue.type,
            config_path=str(config_path),
            success=True,
            message="Fixed",
            backup_path=str(backup_path) if backup_path else None,
        )
    except Exception as exc:
        if backup_path and config_path.exists():
            try:
                shutil.copy2(backup_path, config_path)
            except OSError:
                pass
        return FixResult(
            cli=plugin.name,
            issue_type=issue.type,
            config_path=str(config_path),
            success=False,
            message=f"Exception: {exc}",
            backup_path=str(backup_path) if backup_path else None,
        )


def fix_all_issues(cache: AgentCache, interactive: bool = True) -> list[FixResult]:
    """Fix all detected issues, optionally with user confirmation."""
    results: list[FixResult] = []
    from plugins import discover_plugins

    for plugin in discover_plugins():
        cli_state = cache.clis.get(plugin.name) or {}
        if not cli_state.get("installed"):
            continue

        for issue in plugin.detect_issues():
            if not issue.fix_available:
                continue
            if interactive and sys.stdin.isatty():
                prompt = f"{plugin.name}: apply fix for {issue.type}? [y/N] "
                ans = input(prompt).strip().lower()
                if ans not in {"y", "yes"}:
                    continue
            results.append(apply_fix_safely(plugin, issue))
    return results


def _override_plugin_config_paths(plugin: CLIPlugin, config: Path) -> None:
    # All Tier 1 plugins currently inherit from SimpleCLIPlugin, which stores config paths
    # in `_config_paths`. Override on the instance for this run.
    if hasattr(plugin, "_config_paths"):
        setattr(plugin, "_config_paths", [config])


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="daplug CLI config fixer")
    p.add_argument("--cli", help="Fix a specific CLI (codex/opencode/gemini/claude)")
    p.add_argument("--config", help="Override config path (for testing)")
    p.add_argument("--dry-run", action="store_true", help="Show what would be fixed without applying changes")
    p.add_argument("--non-interactive", action="store_true", help="Do not prompt for confirmation")
    p.add_argument("--json", action="store_true", help="Output machine-readable JSON")
    return p


def main(argv: Optional[list[str]] = None) -> int:
    args = _build_parser().parse_args(argv)

    if args.dry_run:
        from plugins import discover_plugins, get_plugin

        if args.cli:
            plugin = get_plugin(args.cli)
            if plugin is None:
                print(f"Unknown CLI plugin: {args.cli}", file=sys.stderr)
                return 2
            plugins_to_check = [plugin]
        else:
            plugins_to_check = list(discover_plugins())

        fixable: list[dict[str, Any]] = []
        for plugin in plugins_to_check:
            installed, _ = plugin.detect_installation()
            if not installed:
                continue
            for issue in plugin.detect_issues():
                if not issue.fix_available:
                    continue
                fixable.append({
                    "cli": plugin.name,
                    "issue_type": issue.type,
                    "severity": issue.severity,
                    "fix_description": issue.fix_description or "Apply fix",
                    "config_path": issue.config_path or "",
                })

        if args.json:
            print(json.dumps(fixable, indent=2, sort_keys=True))
        else:
            if not fixable:
                print("No fixable issues detected.")
            else:
                print(f"Would fix {len(fixable)} issue(s):\n")
                for item in fixable:
                    print(f"  {item['cli']}: {item['issue_type']} - {item['fix_description']}")
                print("\nRun without --dry-run to apply fixes.")
        return 0

    if args.cli:
        from plugins import get_plugin

        plugin = get_plugin(args.cli)
        if plugin is None:
            print(f"Unknown CLI plugin: {args.cli}", file=sys.stderr)
            return 2
        if args.config:
            _override_plugin_config_paths(plugin, Path(args.config))

        issues = [i for i in plugin.detect_issues() if i.fix_available]
        results = [apply_fix_safely(plugin, i) for i in issues]
    else:
        from detector import scan_all_clis

        cache = scan_all_clis(force_refresh=True)
        results = fix_all_issues(cache, interactive=not args.non_interactive)

    if args.json:
        print(json.dumps([r.__dict__ for r in results], indent=2, sort_keys=True))
    else:
        for r in results:
            status = "OK" if r.success else "FAIL"
            extra = f" (backup: {r.backup_path})" if r.backup_path else ""
            print(f"{status}\t{r.cli}\t{r.issue_type}\t{r.config_path}{extra}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
