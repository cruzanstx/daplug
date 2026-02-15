#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


PLUGIN_ID = "daplug@cruzanstx"
DEFAULT_OUTPUT_DIR = Path.home() / ".config" / "opencode" / "commands"


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


def _render_bridge(command_name: str, command_spec: Path) -> str:
    spec_path = command_spec.resolve()
    return (
        "---\n"
        f'description: "daplug: {command_name}"\n'
        "---\n"
        "\n"
        f"You are executing daplug's `{command_name}` command.\n"
        "\n"
        "Read and follow this command spec exactly:\n"
        f"@{spec_path}\n"
        "\n"
        "User arguments: $ARGUMENTS\n"
        "\n"
        "Execute the command behavior exactly as documented.\n"
        "Do not invent alternative workflows.\n"
    )


def _clean_stale_bridges(output_dir: Path) -> int:
    removed = 0
    for path in output_dir.glob("daplug-*.md"):
        try:
            path.unlink()
            removed += 1
        except FileNotFoundError:
            continue
    return removed


def generate_bridges(*, plugin_root: Path, output_dir: Path, clean: bool) -> int:
    command_specs = _iter_command_specs(plugin_root)
    commands_dir = plugin_root / "commands"
    if not command_specs:
        print(f"No command specs found under {commands_dir}", file=sys.stderr)
        return 0

    output_dir.mkdir(parents=True, exist_ok=True)

    removed = 0
    if clean:
        removed = _clean_stale_bridges(output_dir)
        print(f"Removed {removed} stale bridge(s) from {output_dir}")

    generated = 0
    for spec in command_specs:
        command_name = spec.stem
        bridge_path = output_dir / f"daplug-{command_name}.md"
        bridge_path.write_text(_render_bridge(command_name, spec), encoding="utf-8")
        print(f"Generated {bridge_path}")
        generated += 1

    print(
        f"\nSummary: generated {generated} bridge(s) into {output_dir} "
        f"(plugin_root={plugin_root}, cleaned={removed})"
    )
    return generated


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        description="Generate OpenCode-compatible daplug command bridge wrappers."
    )
    parser.add_argument(
        "output_dir",
        nargs="?",
        default=str(DEFAULT_OUTPUT_DIR),
        help=f"Output directory for bridge commands (default: {DEFAULT_OUTPUT_DIR})",
    )
    parser.add_argument(
        "--clean",
        action="store_true",
        help="Remove existing daplug-*.md bridges from the output directory before regenerating.",
    )
    args = parser.parse_args(argv)

    plugin_root = find_plugin_root()
    output_dir = Path(args.output_dir).expanduser()

    generated = generate_bridges(plugin_root=plugin_root, output_dir=output_dir, clean=args.clean)
    return 0 if generated > 0 else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

