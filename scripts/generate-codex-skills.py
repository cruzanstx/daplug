#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path


PLUGIN_ID = "daplug@cruzanstx"
DEFAULT_OUTPUT_DIR = Path.home() / ".codex" / "skills" / "daplug"
DEFAULT_LEGACY_PROMPTS_DIR = Path.home() / ".codex" / "prompts"
LEGACY_ARCHIVE_DIR_NAME = ".archive-pre-bridge"
SKILL_SENTINEL = "<!-- daplug-skill: managed; do not edit -->"
LEGACY_BRIDGE_SENTINEL = "<!-- daplug-bridge: managed; do not edit -->"


def find_plugin_root() -> Path:
    """Prefer Claude's installed plugin location; fall back to this repo checkout."""

    manifest = Path.home() / ".claude" / "plugins" / "installed_plugins.json"
    if manifest.is_file():
        try:
            data = json.loads(manifest.read_text(encoding="utf-8"))
            plugins = data.get("plugins") or {}
            entries = plugins.get(PLUGIN_ID) or []
            if isinstance(entries, list) and entries:
                install_path = entries[0].get("installPath")
                if install_path:
                    root = Path(install_path).expanduser()
                    if root.is_dir():
                        return root
        except Exception as e:
            print(f"Warning: failed to read {manifest}: {e}", file=sys.stderr)

    return Path(__file__).resolve().parent.parent


def _iter_command_specs(plugin_root: Path) -> list[Path]:
    commands_dir = plugin_root / "commands"
    if not commands_dir.is_dir():
        return []
    return sorted(commands_dir.glob("*.md"))


def _parse_frontmatter(spec: Path) -> dict[str, str]:
    """Parse top-level scalar YAML fields from a command spec's frontmatter."""
    try:
        text = spec.read_text(encoding="utf-8")
    except OSError:
        return {}
    match = re.match(r"^---\s*\n(.*?)\n---\s*\n", text, flags=re.DOTALL)
    if not match:
        return {}
    fields: dict[str, str] = {}
    for line in match.group(1).splitlines():
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        key = key.strip()
        value = value.strip()
        if value.startswith('"') and value.endswith('"'):
            value = value[1:-1]
        fields[key] = value
    return fields


def _render_skill(command_name: str, command_spec: Path, fields: dict[str, str]) -> str:
    spec_path = command_spec.resolve()
    description = fields.get("description", f"Run daplug's `{command_name}` command.")
    argument_hint = fields.get("argument-hint", "").strip()
    description = description.replace("\n", " ")

    body = [
        "---",
        f"name: {command_name}",
        f"description: {description}",
        "---",
        SKILL_SENTINEL,
        "",
        f"# daplug `{command_name}`",
        "",
        f"Execute daplug's `{command_name}` command. The canonical command specification is at:",
        "",
        f"  {spec_path}",
        "",
        "## When invoked",
        "",
        "1. Read the spec file at the path above.",
        "2. Execute it exactly as documented, using the user-provided arguments.",
        "3. Do not invent alternative workflows.",
        "",
    ]
    if argument_hint:
        body.extend(
            [
                "## Argument hint",
                "",
                f"`{argument_hint}`",
                "",
            ]
        )
    return "\n".join(body)


def _is_managed_skill(skill_md: Path) -> bool:
    try:
        return SKILL_SENTINEL in skill_md.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return False


def _is_legacy_bridge(path: Path) -> bool:
    try:
        return LEGACY_BRIDGE_SENTINEL in path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return False


def _clean_managed_skills(output_dir: Path) -> int:
    removed = 0
    if not output_dir.is_dir():
        return 0
    for skill_md in output_dir.glob("*/SKILL.md"):
        if _is_managed_skill(skill_md):
            try:
                skill_dir = skill_md.parent
                skill_md.unlink()
                if not any(skill_dir.iterdir()):
                    skill_dir.rmdir()
                removed += 1
            except FileNotFoundError:
                continue
    return removed


def migrate_legacy_prompt_bridges(prompts_dir: Path) -> tuple[int, int]:
    """Remove sentinel-tagged legacy bridges and restore archived hand-ports."""
    if not prompts_dir.is_dir():
        return 0, 0
    archive = prompts_dir / LEGACY_ARCHIVE_DIR_NAME
    removed = 0
    restored = 0
    for path in list(prompts_dir.glob("*.md")):
        if not _is_legacy_bridge(path):
            continue
        try:
            path.unlink()
            removed += 1
        except FileNotFoundError:
            continue
        archived = archive / path.name
        if archived.is_file():
            try:
                archived.replace(path)
                restored += 1
            except OSError:
                continue
    if archive.is_dir():
        try:
            if not any(archive.iterdir()):
                archive.rmdir()
        except OSError:
            pass
    return removed, restored


def generate_skills(
    *,
    plugin_root: Path,
    output_dir: Path,
    clean: bool,
    migrate_prompts_dir: Path | None,
) -> int:
    command_specs = _iter_command_specs(plugin_root)
    commands_dir = plugin_root / "commands"
    if not command_specs:
        print(f"No command specs found under {commands_dir}", file=sys.stderr)
        return 0

    output_dir.mkdir(parents=True, exist_ok=True)

    if clean:
        removed = _clean_managed_skills(output_dir)
        print(f"Removed {removed} stale managed skill(s) from {output_dir}")

    generated = 0
    for spec in command_specs:
        command_name = spec.stem
        fields = _parse_frontmatter(spec)
        skill_dir = output_dir / command_name
        skill_dir.mkdir(parents=True, exist_ok=True)
        skill_path = skill_dir / "SKILL.md"
        skill_path.write_text(
            _render_skill(command_name, spec, fields),
            encoding="utf-8",
        )
        print(f"Generated {skill_path}")
        generated += 1

    migrate_removed = 0
    migrate_restored = 0
    if migrate_prompts_dir is not None:
        migrate_removed, migrate_restored = migrate_legacy_prompt_bridges(migrate_prompts_dir)
        if migrate_removed or migrate_restored:
            print(
                f"Migrated legacy prompt bridges in {migrate_prompts_dir}: "
                f"removed {migrate_removed}, restored {migrate_restored} hand-port(s)"
            )

    print(
        f"\nSummary: generated {generated} skill(s) into {output_dir} "
        f"(plugin_root={plugin_root}, "
        f"legacy_removed={migrate_removed}, legacy_restored={migrate_restored})"
    )
    return generated


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Generate Codex skill wrappers for daplug commands at "
            f"{DEFAULT_OUTPUT_DIR}. Skills are invoked via $<command-name> "
            "(or auto-triggered by description match)."
        )
    )
    parser.add_argument(
        "output_dir",
        nargs="?",
        default=str(DEFAULT_OUTPUT_DIR),
        help=f"Output directory for skill folders (default: {DEFAULT_OUTPUT_DIR})",
    )
    parser.add_argument(
        "--clean",
        action="store_true",
        help="Remove existing managed daplug skills (sentinel-identified) before regenerating.",
    )
    parser.add_argument(
        "--no-migrate",
        action="store_true",
        help=(
            "Skip cleanup of v0.26.0 legacy prompt bridges at "
            f"{DEFAULT_LEGACY_PROMPTS_DIR}. By default this script removes "
            "any sentinel-tagged bridge files there and restores archived hand-ports."
        ),
    )
    parser.add_argument(
        "--legacy-prompts-dir",
        default=str(DEFAULT_LEGACY_PROMPTS_DIR),
        help=f"Override legacy prompts dir for migration (default: {DEFAULT_LEGACY_PROMPTS_DIR})",
    )
    args = parser.parse_args(argv)

    plugin_root = find_plugin_root()
    output_dir = Path(args.output_dir).expanduser()
    migrate_dir = None if args.no_migrate else Path(args.legacy_prompts_dir).expanduser()

    generated = generate_skills(
        plugin_root=plugin_root,
        output_dir=output_dir,
        clean=args.clean,
        migrate_prompts_dir=migrate_dir,
    )
    return 0 if generated > 0 else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
