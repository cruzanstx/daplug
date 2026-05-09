#!/usr/bin/env python3
"""Tests for the Codex skill generator."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

_parent = str(Path(__file__).resolve().parent.parent)
if _parent not in sys.path:
    sys.path.insert(0, _parent)

mod = importlib.import_module("generate-codex-skills")

_iter_command_specs = mod._iter_command_specs
_parse_frontmatter = mod._parse_frontmatter
_render_skill = mod._render_skill
_is_managed_skill = mod._is_managed_skill
_is_legacy_bridge = mod._is_legacy_bridge
_clean_managed_skills = mod._clean_managed_skills
migrate_legacy_prompt_bridges = mod.migrate_legacy_prompt_bridges
generate_skills = mod.generate_skills
main = mod.main
SKILL_SENTINEL = mod.SKILL_SENTINEL
LEGACY_BRIDGE_SENTINEL = mod.LEGACY_BRIDGE_SENTINEL
LEGACY_ARCHIVE_DIR_NAME = mod.LEGACY_ARCHIVE_DIR_NAME


@pytest.fixture
def fake_plugin(tmp_path: Path) -> Path:
    commands = tmp_path / "commands"
    commands.mkdir()
    (commands / "run-prompt.md").write_text(
        "---\n"
        "name: run-prompt\n"
        "description: Execute prompts from ./prompts/ with various AI models\n"
        "argument-hint: <prompt> [--model codex]\n"
        "---\n"
        "Body of run-prompt command.\n"
    )
    (commands / "worktree.md").write_text(
        "---\nname: worktree\ndescription: Manage git worktrees\n---\nBody.\n"
    )
    (commands / "no-frontmatter.md").write_text("Just body, no frontmatter.\n")
    return tmp_path


@pytest.fixture
def output_dir(tmp_path: Path) -> Path:
    return tmp_path / "skills"


class TestIterCommandSpecs:
    def test_finds_md_files(self, fake_plugin: Path):
        specs = _iter_command_specs(fake_plugin)
        assert len(specs) == 3

    def test_missing_commands_dir(self, tmp_path: Path):
        assert _iter_command_specs(tmp_path) == []


class TestParseFrontmatter:
    def test_parses_basic_fields(self, fake_plugin: Path):
        fields = _parse_frontmatter(fake_plugin / "commands" / "run-prompt.md")
        assert fields["name"] == "run-prompt"
        assert "Execute prompts" in fields["description"]
        assert fields["argument-hint"].startswith("<prompt>")

    def test_handles_no_frontmatter(self, fake_plugin: Path):
        fields = _parse_frontmatter(fake_plugin / "commands" / "no-frontmatter.md")
        assert fields == {}

    def test_strips_quoted_values(self, tmp_path: Path):
        spec = tmp_path / "x.md"
        spec.write_text('---\nname: foo\nargument-hint: "[--clean]"\n---\nbody\n')
        fields = _parse_frontmatter(spec)
        assert fields["argument-hint"] == "[--clean]"


class TestRenderSkill:
    def test_contains_frontmatter(self, fake_plugin: Path):
        spec = fake_plugin / "commands" / "run-prompt.md"
        fields = _parse_frontmatter(spec)
        out = _render_skill("run-prompt", spec, fields)
        assert out.startswith("---\n")
        assert "name: run-prompt" in out
        assert "Execute prompts from ./prompts/" in out

    def test_contains_sentinel(self, fake_plugin: Path):
        spec = fake_plugin / "commands" / "run-prompt.md"
        out = _render_skill("run-prompt", spec, _parse_frontmatter(spec))
        assert SKILL_SENTINEL in out

    def test_contains_spec_path(self, fake_plugin: Path):
        spec = fake_plugin / "commands" / "run-prompt.md"
        out = _render_skill("run-prompt", spec, _parse_frontmatter(spec))
        assert str(spec.resolve()) in out

    def test_contains_argument_hint_when_present(self, fake_plugin: Path):
        spec = fake_plugin / "commands" / "run-prompt.md"
        out = _render_skill("run-prompt", spec, _parse_frontmatter(spec))
        assert "Argument hint" in out
        assert "<prompt>" in out

    def test_omits_argument_hint_when_absent(self, fake_plugin: Path):
        spec = fake_plugin / "commands" / "worktree.md"
        out = _render_skill("worktree", spec, _parse_frontmatter(spec))
        assert "Argument hint" not in out


class TestIsManagedSkill:
    def test_detects_sentinel(self, tmp_path: Path):
        f = tmp_path / "SKILL.md"
        f.write_text(f"---\n---\n{SKILL_SENTINEL}\nbody\n")
        assert _is_managed_skill(f) is True

    def test_rejects_user_skill(self, tmp_path: Path):
        f = tmp_path / "SKILL.md"
        f.write_text("---\nname: user\n---\nuser body\n")
        assert _is_managed_skill(f) is False


class TestCleanManagedSkills:
    def test_removes_managed_only(self, output_dir: Path):
        output_dir.mkdir()
        managed = output_dir / "run-prompt"
        managed.mkdir()
        (managed / "SKILL.md").write_text(f"---\n---\n{SKILL_SENTINEL}\n")
        unmanaged = output_dir / "user-skill"
        unmanaged.mkdir()
        (unmanaged / "SKILL.md").write_text("---\n---\nuser content\n")

        removed = _clean_managed_skills(output_dir)
        assert removed == 1
        assert not managed.exists()
        assert (unmanaged / "SKILL.md").exists()

    def test_missing_dir(self, tmp_path: Path):
        assert _clean_managed_skills(tmp_path / "nope") == 0


class TestMigrateLegacyPromptBridges:
    def test_removes_legacy_bridges_and_restores_handports(self, tmp_path: Path):
        prompts = tmp_path / "prompts"
        prompts.mkdir()
        archive = prompts / LEGACY_ARCHIVE_DIR_NAME
        archive.mkdir()

        bridge = prompts / "run-prompt.md"
        bridge.write_text(f"---\n---\n{LEGACY_BRIDGE_SENTINEL}\nbridge body\n")
        archived = archive / "run-prompt.md"
        archived.write_text("original hand-port content")

        unrelated = prompts / "playwright.md"
        unrelated.write_text("user's other prompt")

        removed, restored = migrate_legacy_prompt_bridges(prompts)
        assert removed == 1
        assert restored == 1
        assert bridge.exists()
        assert bridge.read_text() == "original hand-port content"
        assert unrelated.exists()
        assert not archive.exists()  # cleaned up empty dir

    def test_removes_bridge_with_no_archive(self, tmp_path: Path):
        prompts = tmp_path / "prompts"
        prompts.mkdir()
        bridge = prompts / "run-prompt.md"
        bridge.write_text(f"---\n---\n{LEGACY_BRIDGE_SENTINEL}\nbridge body\n")

        removed, restored = migrate_legacy_prompt_bridges(prompts)
        assert removed == 1
        assert restored == 0
        assert not bridge.exists()

    def test_missing_dir_is_noop(self, tmp_path: Path):
        removed, restored = migrate_legacy_prompt_bridges(tmp_path / "nope")
        assert removed == 0
        assert restored == 0

    def test_skips_non_managed_files(self, tmp_path: Path):
        prompts = tmp_path / "prompts"
        prompts.mkdir()
        user_md = prompts / "user.md"
        user_md.write_text("user content, no sentinel")

        removed, restored = migrate_legacy_prompt_bridges(prompts)
        assert removed == 0
        assert restored == 0
        assert user_md.exists()


class TestGenerateSkills:
    def test_creates_skill_folders(self, fake_plugin: Path, output_dir: Path):
        count = generate_skills(
            plugin_root=fake_plugin,
            output_dir=output_dir,
            clean=False,
            migrate_prompts_dir=None,
        )
        assert count == 3
        assert (output_dir / "run-prompt" / "SKILL.md").is_file()
        assert (output_dir / "worktree" / "SKILL.md").is_file()
        assert (output_dir / "no-frontmatter" / "SKILL.md").is_file()

    def test_skill_content_includes_sentinel(self, fake_plugin: Path, output_dir: Path):
        generate_skills(
            plugin_root=fake_plugin,
            output_dir=output_dir,
            clean=False,
            migrate_prompts_dir=None,
        )
        body = (output_dir / "run-prompt" / "SKILL.md").read_text()
        assert SKILL_SENTINEL in body
        assert "Execute prompts" in body
        assert "<prompt>" in body  # arg hint preserved

    def test_clean_removes_managed_then_regenerates(self, fake_plugin: Path, output_dir: Path):
        output_dir.mkdir()
        stale = output_dir / "stale-cmd"
        stale.mkdir()
        (stale / "SKILL.md").write_text(f"---\n---\n{SKILL_SENTINEL}\nstale\n")
        # User-installed skill that must NOT be touched
        user = output_dir / "user-skill"
        user.mkdir()
        (user / "SKILL.md").write_text("user content")

        generate_skills(
            plugin_root=fake_plugin,
            output_dir=output_dir,
            clean=True,
            migrate_prompts_dir=None,
        )
        assert not stale.exists()
        assert (user / "SKILL.md").exists()
        assert (output_dir / "run-prompt" / "SKILL.md").exists()

    def test_migrate_runs_when_dir_provided(self, fake_plugin: Path, output_dir: Path, tmp_path: Path):
        prompts = tmp_path / "prompts"
        prompts.mkdir()
        bridge = prompts / "run-prompt.md"
        bridge.write_text(f"---\n---\n{LEGACY_BRIDGE_SENTINEL}\nbridge\n")

        generate_skills(
            plugin_root=fake_plugin,
            output_dir=output_dir,
            clean=False,
            migrate_prompts_dir=prompts,
        )
        assert not bridge.exists()

    def test_migrate_skipped_when_none(self, fake_plugin: Path, output_dir: Path, tmp_path: Path):
        prompts = tmp_path / "prompts"
        prompts.mkdir()
        bridge = prompts / "run-prompt.md"
        bridge.write_text(f"---\n---\n{LEGACY_BRIDGE_SENTINEL}\nbridge\n")

        generate_skills(
            plugin_root=fake_plugin,
            output_dir=output_dir,
            clean=False,
            migrate_prompts_dir=None,
        )
        assert bridge.exists()

    def test_no_commands_returns_zero(self, tmp_path: Path, output_dir: Path):
        (tmp_path / "commands").mkdir()
        count = generate_skills(
            plugin_root=tmp_path,
            output_dir=output_dir,
            clean=False,
            migrate_prompts_dir=None,
        )
        assert count == 0


class TestMain:
    def test_returns_zero_on_success(self, fake_plugin: Path, output_dir: Path, monkeypatch):
        monkeypatch.setattr(mod, "find_plugin_root", lambda: fake_plugin)
        rc = main([str(output_dir), "--no-migrate"])
        assert rc == 0
        assert (output_dir / "run-prompt" / "SKILL.md").exists()

    def test_returns_one_on_no_commands(self, tmp_path: Path, output_dir: Path, monkeypatch):
        (tmp_path / "commands").mkdir()
        monkeypatch.setattr(mod, "find_plugin_root", lambda: tmp_path)
        rc = main([str(output_dir), "--no-migrate"])
        assert rc == 1

    def test_clean_flag(self, fake_plugin: Path, output_dir: Path, monkeypatch):
        monkeypatch.setattr(mod, "find_plugin_root", lambda: fake_plugin)
        output_dir.mkdir()
        stale = output_dir / "stale"
        stale.mkdir()
        (stale / "SKILL.md").write_text(f"---\n---\n{SKILL_SENTINEL}\nstale\n")
        main(["--clean", "--no-migrate", str(output_dir)])
        assert not stale.exists()

    def test_migrate_default_runs(self, fake_plugin: Path, output_dir: Path, tmp_path: Path, monkeypatch):
        monkeypatch.setattr(mod, "find_plugin_root", lambda: fake_plugin)
        prompts = tmp_path / "prompts"
        prompts.mkdir()
        bridge = prompts / "run-prompt.md"
        bridge.write_text(f"---\n---\n{LEGACY_BRIDGE_SENTINEL}\nbridge\n")
        main([str(output_dir), "--legacy-prompts-dir", str(prompts)])
        assert not bridge.exists()
