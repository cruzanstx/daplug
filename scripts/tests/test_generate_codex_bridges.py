#!/usr/bin/env python3
"""Tests for the Codex command bridge generator."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

# The module file uses a hyphen; import via importlib.
_parent = str(Path(__file__).resolve().parent.parent)
if _parent not in sys.path:
    sys.path.insert(0, _parent)

generate_codex_bridges = importlib.import_module("generate-codex-bridges")

_clean_stale_bridges = generate_codex_bridges._clean_stale_bridges
_iter_command_specs = generate_codex_bridges._iter_command_specs
_render_bridge = generate_codex_bridges._render_bridge
_is_managed_bridge = generate_codex_bridges._is_managed_bridge
_archive_handport = generate_codex_bridges._archive_handport
generate_bridges = generate_codex_bridges.generate_bridges
main = generate_codex_bridges.main
BRIDGE_SENTINEL = generate_codex_bridges.BRIDGE_SENTINEL
ARCHIVE_DIR_NAME = generate_codex_bridges.ARCHIVE_DIR_NAME


@pytest.fixture
def fake_plugin(tmp_path: Path) -> Path:
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


class TestRenderBridge:
    def test_contains_frontmatter(self):
        output = _render_bridge("run-prompt", Path("/fake/commands/run-prompt.md"))
        assert output.startswith("---\n")
        assert 'description: "daplug: run-prompt"' in output

    def test_contains_sentinel(self):
        output = _render_bridge("run-prompt", Path("/fake/commands/run-prompt.md"))
        assert BRIDGE_SENTINEL in output

    def test_contains_spec_reference(self, fake_plugin: Path):
        spec = fake_plugin / "commands" / "run-prompt.md"
        output = _render_bridge("run-prompt", spec)
        assert str(spec.resolve()) in output

    def test_no_at_prefix(self, fake_plugin: Path):
        spec = fake_plugin / "commands" / "run-prompt.md"
        output = _render_bridge("run-prompt", spec)
        assert f"@{spec.resolve()}" not in output

    def test_contains_arguments_placeholder(self):
        output = _render_bridge("test-cmd", Path("/fake/commands/test-cmd.md"))
        assert "$ARGUMENTS" in output

    def test_contains_command_name(self):
        output = _render_bridge("worktree", Path("/fake/commands/worktree.md"))
        assert "`worktree`" in output


class TestIsManagedBridge:
    def test_detects_sentinel(self, output_dir: Path):
        managed = output_dir / "x.md"
        managed.write_text(f"---\n---\n{BRIDGE_SENTINEL}\nbody\n")
        assert _is_managed_bridge(managed) is True

    def test_rejects_non_managed(self, output_dir: Path):
        handport = output_dir / "y.md"
        handport.write_text("---\n---\nuser content\n")
        assert _is_managed_bridge(handport) is False

    def test_handles_missing_file(self, output_dir: Path):
        assert _is_managed_bridge(output_dir / "nope.md") is False


class TestArchiveHandport:
    def test_moves_file_to_archive(self, output_dir: Path):
        handport = output_dir / "run-prompt.md"
        handport.write_text("user content")
        archive_dir = output_dir / ARCHIVE_DIR_NAME
        dest = _archive_handport(handport, archive_dir)
        assert not handport.exists()
        assert dest.exists()
        assert dest.read_text() == "user content"
        assert dest.parent == archive_dir

    def test_handles_collision_in_archive(self, output_dir: Path):
        archive_dir = output_dir / ARCHIVE_DIR_NAME
        archive_dir.mkdir()
        (archive_dir / "run-prompt.md").write_text("older archive")
        handport = output_dir / "run-prompt.md"
        handport.write_text("newer content")
        dest = _archive_handport(handport, archive_dir)
        assert dest.exists()
        assert dest.name != "run-prompt.md"
        assert (archive_dir / "run-prompt.md").read_text() == "older archive"
        assert dest.read_text() == "newer content"


class TestCleanStaleBridges:
    def test_removes_managed_files_only(self, output_dir: Path):
        managed = output_dir / "run-prompt.md"
        managed.write_text(f"---\n---\n{BRIDGE_SENTINEL}\nbridge\n")
        handport = output_dir / "kept.md"
        handport.write_text("user content")
        removed = _clean_stale_bridges(output_dir)
        assert removed == 1
        assert not managed.exists()
        assert handport.exists()

    def test_no_managed_files(self, output_dir: Path):
        (output_dir / "user.md").write_text("user content")
        assert _clean_stale_bridges(output_dir) == 0
        assert (output_dir / "user.md").exists()

    def test_empty_dir(self, tmp_path: Path):
        empty = tmp_path / "empty"
        empty.mkdir()
        assert _clean_stale_bridges(empty) == 0

    def test_missing_dir(self, tmp_path: Path):
        assert _clean_stale_bridges(tmp_path / "nope") == 0


class TestGenerateBridges:
    def test_generates_all_bridges_with_bare_names(self, fake_plugin: Path, output_dir: Path):
        count = generate_bridges(plugin_root=fake_plugin, output_dir=output_dir, clean=False)
        assert count == 3
        names = sorted(p.name for p in output_dir.glob("*.md"))
        assert names == ["prompts.md", "run-prompt.md", "worktree.md"]

    def test_no_daplug_prefix(self, fake_plugin: Path, output_dir: Path):
        generate_bridges(plugin_root=fake_plugin, output_dir=output_dir, clean=False)
        assert not list(output_dir.glob("daplug-*.md"))

    def test_bridge_content_includes_sentinel(self, fake_plugin: Path, output_dir: Path):
        generate_bridges(plugin_root=fake_plugin, output_dir=output_dir, clean=False)
        bridge = (output_dir / "run-prompt.md").read_text()
        assert BRIDGE_SENTINEL in bridge
        assert "daplug: run-prompt" in bridge
        assert "$ARGUMENTS" in bridge

    def test_archives_existing_handport(self, fake_plugin: Path, output_dir: Path):
        handport = output_dir / "run-prompt.md"
        handport.write_text("hand-port content")
        generate_bridges(plugin_root=fake_plugin, output_dir=output_dir, clean=False)
        archive = output_dir / ARCHIVE_DIR_NAME / "run-prompt.md"
        assert archive.exists()
        assert archive.read_text() == "hand-port content"
        assert _is_managed_bridge(handport)

    def test_does_not_archive_managed_bridge(self, fake_plugin: Path, output_dir: Path):
        existing = output_dir / "run-prompt.md"
        existing.write_text(f"---\n---\n{BRIDGE_SENTINEL}\nold bridge\n")
        generate_bridges(plugin_root=fake_plugin, output_dir=output_dir, clean=False)
        assert not (output_dir / ARCHIVE_DIR_NAME).exists()
        assert _is_managed_bridge(existing)

    def test_does_not_touch_unrelated_files(self, fake_plugin: Path, output_dir: Path):
        unrelated = output_dir / "playwright_codex.md"
        unrelated.write_text("user's other prompt")
        generate_bridges(plugin_root=fake_plugin, output_dir=output_dir, clean=False)
        assert unrelated.exists()
        assert unrelated.read_text() == "user's other prompt"

    def test_clean_only_removes_managed(self, fake_plugin: Path, output_dir: Path):
        unrelated = output_dir / "user.md"
        unrelated.write_text("user")
        old_bridge = output_dir / "old.md"
        old_bridge.write_text(f"---\n---\n{BRIDGE_SENTINEL}\nold\n")
        generate_bridges(plugin_root=fake_plugin, output_dir=output_dir, clean=True)
        assert not old_bridge.exists()
        assert unrelated.exists()
        assert (output_dir / "run-prompt.md").exists()

    def test_creates_output_dir(self, fake_plugin: Path, tmp_path: Path):
        new_dir = tmp_path / "new" / "nested"
        count = generate_bridges(plugin_root=fake_plugin, output_dir=new_dir, clean=False)
        assert count == 3
        assert new_dir.is_dir()

    def test_no_commands_returns_zero(self, tmp_path: Path, output_dir: Path):
        (tmp_path / "commands").mkdir()
        count = generate_bridges(plugin_root=tmp_path, output_dir=output_dir, clean=False)
        assert count == 0


class TestMain:
    def test_returns_zero_on_success(self, fake_plugin: Path, output_dir: Path, monkeypatch):
        monkeypatch.setattr(
            generate_codex_bridges, "find_plugin_root", lambda: fake_plugin
        )
        assert main([str(output_dir)]) == 0

    def test_returns_one_on_no_commands(self, tmp_path: Path, output_dir: Path, monkeypatch):
        (tmp_path / "commands").mkdir()
        monkeypatch.setattr(
            generate_codex_bridges, "find_plugin_root", lambda: tmp_path
        )
        assert main([str(output_dir)]) == 1

    def test_clean_flag(self, fake_plugin: Path, output_dir: Path, monkeypatch):
        monkeypatch.setattr(
            generate_codex_bridges, "find_plugin_root", lambda: fake_plugin
        )
        old_bridge = output_dir / "stale.md"
        old_bridge.write_text(f"---\n---\n{BRIDGE_SENTINEL}\nstale\n")
        main(["--clean", str(output_dir)])
        assert not old_bridge.exists()
