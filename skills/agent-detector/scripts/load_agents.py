#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from cache import default_cache_path
from detector import scan_all_clis
from plugins import discover_plugins
from providers import discover_providers


@dataclass
class FixResult:
    cli: str
    issue_type: str
    ok: bool
    details: str = ""


def _render_markdown_table(headers: list[str], rows: list[list[str]]) -> str:
    safe_rows = [[(cell or "").replace("\n", " ") for cell in row] for row in rows]
    widths = [len(h) for h in headers]
    for row in safe_rows:
        for i, cell in enumerate(row):
            if i < len(widths):
                widths[i] = max(widths[i], len(cell))

    def fmt_row(cols: list[str]) -> str:
        padded = [cols[i].ljust(widths[i]) for i in range(len(headers))]
        return "| " + " | ".join(padded) + " |"

    sep = "| " + " | ".join("-" * w for w in widths) + " |"
    lines = [fmt_row(headers), sep]
    for row in safe_rows:
        row = (row + [""] * len(headers))[: len(headers)]
        lines.append(fmt_row(row))
    return "\n".join(lines)


def _model_summary(models: list[dict[str, Any]], max_items: int = 3) -> str:
    ids: list[str] = []
    for m in models:
        raw = str(m.get("id") or "").strip()
        if not raw:
            continue
        if ":" in raw:
            _, rest = raw.split(":", 1)
        else:
            rest = raw
        ids.append(rest)

    # Deduplicate while preserving order
    seen: set[str] = set()
    unique: list[str] = []
    for item in ids:
        if item in seen:
            continue
        seen.add(item)
        unique.append(item)

    if not unique:
        return "-"
    shown = unique[:max_items]
    suffix = ", …" if len(unique) > max_items else ""
    return ", ".join(shown) + suffix


def _cli_label(cli_name: str) -> str:
    # Prefer UX-friendly labels for display.
    if cli_name == "claude":
        return "claude-code"
    return cli_name


def _not_installed_recommendations() -> list[tuple[str, str]]:
    recs: list[tuple[str, str]] = []
    if shutil.which("aider") is None:
        recs.append(("aider", "pip install aider-chat"))
    if shutil.which("goose") is None:
        recs.append(("goose", "brew install goose"))
    return recs


def _clear_cache_files() -> list[Path]:
    cleared: list[Path] = []
    candidates = [default_cache_path(), Path("/tmp/daplug-agents.json")]
    for path in candidates:
        try:
            if path.exists():
                path.unlink()
                cleared.append(path)
        except OSError:
            continue
    return cleared


def _collect_issues(cache: dict[str, Any]) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    clis = cache.get("clis") or {}
    if not isinstance(clis, dict):
        return issues
    for cli_name, info in clis.items():
        if not isinstance(info, dict):
            continue
        if not info.get("installed"):
            continue
        for issue in info.get("issues") or []:
            if not isinstance(issue, dict):
                continue
            issues.append({"cli": cli_name, **issue})
    return issues


def _fix_all() -> list[FixResult]:
    results: list[FixResult] = []
    for plugin in discover_plugins():
        installed, _exe = plugin.detect_installation()
        if not installed:
            continue
        for issue in plugin.detect_issues():
            if not issue.fix_available:
                continue
            ok = plugin.apply_fix(issue)
            details = ""
            fix_info = getattr(plugin, "_last_fix_info", None)
            if isinstance(fix_info, dict):
                details = str(fix_info.get("details") or "")
            results.append(
                FixResult(cli=plugin.name, issue_type=issue.type, ok=ok, details=details)
            )
    return results


def _print_human(cache: dict[str, Any]) -> None:
    clis = cache.get("clis") or {}
    installed_rows: list[list[str]] = []
    installed_count = 0

    for name in sorted(clis.keys()):
        info = clis.get(name) or {}
        if not isinstance(info, dict) or not info.get("installed"):
            continue
        installed_count += 1
        version = str(info.get("version") or "-")
        models = _model_summary(info.get("models") or [])
        issues = info.get("issues") or []
        issues_count = len(issues) if isinstance(issues, list) else 0
        status = "✅ Ready" if issues_count == 0 else f"⚠️ {issues_count} issue" + ("s" if issues_count != 1 else "")
        installed_rows.append([_cli_label(name), version, models, status])

    print(f"\n✅ Found {installed_count} installed CLIs:\n")
    if installed_rows:
        print(_render_markdown_table(["CLI", "Version", "Models", "Status"], installed_rows))
    else:
        print("_No supported CLIs detected in PATH._")

    # Providers
    providers_by_name = {p.name: p for p in discover_providers()}
    provider_rows: list[list[str]] = []
    union_compatible: set[str] = set()
    providers = cache.get("providers") or {}
    if isinstance(providers, dict):
        for name in sorted(providers.keys()):
            info = providers.get(name) or {}
            if not isinstance(info, dict):
                continue
            union_compatible.update(str(x) for x in (info.get("compatible_clis") or []) if x)
            display_name = name
            plugin = providers_by_name.get(name)
            if plugin is not None:
                display_name = plugin.display_name

            running = bool(info.get("running"))
            endpoint = str(info.get("endpoint") or "")
            endpoint_cell = endpoint if running else "(not running)"
            loaded = info.get("loaded_models") or []
            loaded_cell = "-"
            if running and isinstance(loaded, list) and loaded:
                loaded_cell = ", ".join(str(x) for x in loaded[:5])
                if len(loaded) > 5:
                    loaded_cell += ", …"
            provider_rows.append([display_name, endpoint_cell, loaded_cell])

    print("\n🖥️ Local Model Providers:\n")
    if provider_rows:
        print(_render_markdown_table(["Provider", "Endpoint", "Loaded Models"], provider_rows))
    else:
        print("_No provider plugins registered._")

    if union_compatible:
        known = sorted(union_compatible)
        print(f"\n💡 Local models usable via: {', '.join(known)}")

    # Issues
    issues = _collect_issues(cache)
    if issues:
        print(f"\n⚠️ Issues detected ({len(issues)}):")
        for issue in issues:
            cli = _cli_label(str(issue.get("cli") or ""))
            msg = str(issue.get("message") or issue.get("type") or "Issue")
            print(f"  - {cli}: {msg}")
        if any(bool(i.get("fix_available")) for i in issues):
            print("  - Run `/load-agents --fix` to apply recommended fix(es)")

    # Not installed
    recs = _not_installed_recommendations()
    if recs:
        print("\n❌ Not installed:")
        for name, hint in recs:
            print(f"  - {name} - {hint}")

    cache_path = default_cache_path()
    print(f"\n💾 Saved to {cache_path}")


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="daplug /load-agents helper")
    p.add_argument("--fix", action="store_true", help="Apply recommended safe fixes")
    p.add_argument("--reset", action="store_true", help="Clear cache and rescan")
    p.add_argument("--json", action="store_true", help="Output machine-readable JSON only")
    return p


def _json_payload(cache: dict[str, Any]) -> dict[str, Any]:
    payload = dict(cache)
    payload.setdefault("schema_version", "1.0")
    payload["issues"] = _collect_issues(payload)
    return payload


def main(argv: Optional[list[str]] = None) -> int:
    args = _build_parser().parse_args(argv)

    if args.reset:
        cleared = _clear_cache_files()
        if not args.json:
            if cleared:
                print("🗑️ Cleared agent cache")
            else:
                print("🗑️ Agent cache already clear")
            print("🔍 Rescanning...")

    if args.fix:
        if not args.json:
            print("🔧 Applying fixes...\n")

        # Ensure we start from a fresh scan.
        scan_all_clis(force_refresh=True)
        results = _fix_all()

        if not args.json:
            if not results:
                print("No fixable issues detected.")
            for r in results:
                status = "✅" if r.ok else "❌"
                details = f"\n  {r.details}" if r.details else ""
                print(f"{_cli_label(r.cli)}: {r.issue_type} {status}{details}")

        cache = scan_all_clis(force_refresh=True).to_dict()
        payload = _json_payload(cache)
        if args.json:
            print(json.dumps(payload, indent=2, sort_keys=True))
            return 0

        remaining = payload.get("issues") or []
        if not remaining:
            print("\nAll issues resolved!")
        else:
            print(f"\n⚠️ Remaining issues ({len(remaining)}). Run `/load-agents` to review.")
        return 0

    if not args.json:
        print("🔍 Scanning for AI coding agents...")
    cache_obj = scan_all_clis(force_refresh=bool(args.reset))
    cache = cache_obj.to_dict()
    payload = _json_payload(cache)

    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0

    _print_human(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
