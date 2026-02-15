#!/usr/bin/env python3
"""Tests for the OpenCode command bridge generator."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

# The module file uses a hyphen; import via importlib.
_parent = str(Path(__file__).resolve().parent.parent)
if _parent not in sys.path:
    sys.path.insert(0, _parent)

generate_opencode_bridges = importlib.import_module("generate-opencode-bridges")

_clean_stale_bridges = generate_opencode_bridges._clean_stale_bridges
_iter_command_specs = generate_opencode_bridges._iter_command_specs
_render_bridge = generate_opencode_bridges._render_bridge
generate_bridges = generate_opencode_bridges.generate_bridges
main = generate_opencode_bridges.main


@pytest.fixture
def fake_plugin(tmp_path: Path) -> Path:
    """Create a minimal fake plugin directory with command specs."""
    commands = tmp_path / "commands"
    commands.mkdir()
    (commands / "run-prompt.md").write_text("---\nname: run-prompt\n---\nRun a prompt.\n")
    (commands / "worktree.md").write_text("---\nname: worktree\n---\nManage worktrees.\n")
    (commands / "prompts.md").write_text("---\nname: prompts\n---\nList prompts.\n")
    return tmp_path


@pytest.fixture
def output_dir(tmp_path: Path) -> Path:
    out = tmp_path / "output"
    out.mkdir()
    return out


# --- _iter_command_specs ---


class TestIterCommandSpecs:
    def test_finds_md_files(self, fake_plugin: Path):
        specs = _iter_command_specs(fake_plugin)
        assert len(specs) == 3
        names = [s.stem for s in specs]
        assert "prompts" in names
        assert "run-prompt" in names
        assert "worktree" in names

    def test_sorted_order(self, fake_plugin: Path):
        specs = _iter_command_specs(fake_plugin)
        names = [s.stem for s in specs]
        assert names == sorted(names)

    def test_empty_commands_dir(self, tmp_path: Path):
        (tmp_path / "commands").mkdir()
        assert _iter_command_specs(tmp_path) == []

    def test_missing_commands_dir(self, tmp_path: Path):
        assert _iter_command_specs(tmp_path) == []

    def test_ignores_non_md(self, fake_plugin: Path):
        (fake_plugin / "commands" / "notes.txt").write_text("not a command")
        specs = _iter_command_specs(fake_plugin)
        assert all(s.suffix == ".md" for s in specs)
        assert len(specs) == 3


# --- _render_bridge ---


class TestRenderBridge:
    def test_contains_frontmatter(self):
        output = _render_bridge("run-prompt", Path("/fake/commands/run-prompt.md"))
        assert output.startswith("---\n")
        assert 'description: "daplug: run-prompt"' in output

    def test_contains_spec_reference(self, fake_plugin: Path):
        spec = fake_plugin / "commands" / "run-prompt.md"
        output = _render_bridge("run-prompt", spec)
        assert f"@{spec.resolve()}" in output

    def test_contains_arguments_placeholder(self):
        output = _render_bridge("test-cmd", Path("/fake/commands/test-cmd.md"))
        assert "$ARGUMENTS" in output

    def test_contains_command_name(self):
        output = _render_bridge("worktree", Path("/fake/commands/worktree.md"))
        assert "`worktree`" in output


# --- _clean_stale_bridges ---


class TestCleanStaleBridges:
    def test_removes_daplug_prefixed_files(self, output_dir: Path):
        (output_dir / "daplug-run-prompt.md").write_text("old")
        (output_dir / "daplug-worktree.md").write_text("old")
        removed = _clean_stale_bridges(output_dir)
        assert removed == 2
        assert not list(output_dir.glob("daplug-*.md"))

    def test_preserves_non_daplug_files(self, output_dir: Path):
        (output_dir / "other-tool.md").write_text("keep me")
        (output_dir / "daplug-old.md").write_text("remove me")
        removed = _clean_stale_bridges(output_dir)
        assert removed == 1
        assert (output_dir / "other-tool.md").exists()

    def test_no_files_to_clean(self, output_dir: Path):
        assert _clean_stale_bridges(output_dir) == 0

    def test_empty_dir(self, tmp_path: Path):
        empty = tmp_path / "empty"
        empty.mkdir()
        assert _clean_stale_bridges(empty) == 0


# --- generate_bridges ---


class TestGenerateBridges:
    def test_generates_all_bridges(self, fake_plugin: Path, output_dir: Path):
        count = generate_bridges(plugin_root=fake_plugin, output_dir=output_dir, clean=False)
        assert count == 3
        bridges = list(output_dir.glob("daplug-*.md"))
        assert len(bridges) == 3

    def test_bridge_filenames(self, fake_plugin: Path, output_dir: Path):
        generate_bridges(plugin_root=fake_plugin, output_dir=output_dir, clean=False)
        names = sorted(p.name for p in output_dir.glob("daplug-*.md"))
        assert names == ["daplug-prompts.md", "daplug-run-prompt.md", "daplug-worktree.md"]

    def test_bridge_content_is_valid(self, fake_plugin: Path, output_dir: Path):
        generate_bridges(plugin_root=fake_plugin, output_dir=output_dir, clean=False)
        bridge = (output_dir / "daplug-run-prompt.md").read_text()
        assert "---" in bridge
        assert "daplug: run-prompt" in bridge
        assert "$ARGUMENTS" in bridge

    def test_clean_before_generate(self, fake_plugin: Path, output_dir: Path):
        (output_dir / "daplug-stale.md").write_text("stale")
        generate_bridges(plugin_root=fake_plugin, output_dir=output_dir, clean=True)
        assert not (output_dir / "daplug-stale.md").exists()
        assert len(list(output_dir.glob("daplug-*.md"))) == 3

    def test_creates_output_dir(self, fake_plugin: Path, tmp_path: Path):
        new_dir = tmp_path / "new" / "nested"
        count = generate_bridges(plugin_root=fake_plugin, output_dir=new_dir, clean=False)
        assert count == 3
        assert new_dir.is_dir()

    def test_no_commands_returns_zero(self, tmp_path: Path, output_dir: Path):
        (tmp_path / "commands").mkdir()
        count = generate_bridges(plugin_root=tmp_path, output_dir=output_dir, clean=False)
        assert count == 0


# --- main() CLI ---


class TestMain:
    def test_returns_zero_on_success(self, fake_plugin: Path, output_dir: Path, monkeypatch):
        monkeypatch.setattr(
            generate_opencode_bridges, "find_plugin_root", lambda: fake_plugin
        )
        assert main([str(output_dir)]) == 0

    def test_returns_one_on_no_commands(self, tmp_path: Path, output_dir: Path, monkeypatch):
        (tmp_path / "commands").mkdir()
        monkeypatch.setattr(
            generate_opencode_bridges, "find_plugin_root", lambda: tmp_path
        )
        assert main([str(output_dir)]) == 1

    def test_clean_flag(self, fake_plugin: Path, output_dir: Path, monkeypatch):
        monkeypatch.setattr(
            generate_opencode_bridges, "find_plugin_root", lambda: fake_plugin
        )
        (output_dir / "daplug-old.md").write_text("stale")
        main(["--clean", str(output_dir)])
        assert not (output_dir / "daplug-old.md").exists()
