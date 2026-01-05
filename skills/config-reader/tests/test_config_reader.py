import re
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.append(str(SCRIPT_DIR))

import config  # noqa: E402


def test_parse_block():
    content = """
<daplug_config>
preferred_agent: codex
worktree_dir: .worktrees/
</daplug_config>
"""
    parsed = config.parse_config_content(content)
    assert parsed.format == "block"
    assert parsed.data["preferred_agent"] == "codex"
    assert parsed.data["worktree_dir"] == ".worktrees/"


def test_legacy_fallback():
    content = "preferred_agent: claude\nworktree_dir: ../worktrees\n"
    parsed = config.parse_config_content(content)
    assert parsed.format == "legacy"
    assert parsed.data["preferred_agent"] == "claude"
    assert parsed.data["worktree_dir"] == "../worktrees"


def test_project_overrides_user(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    project_claude = project / "CLAUDE.md"
    project_claude.write_text(
        "<daplug_config>\npreferred_agent: codex\n</daplug_config>\n"
    )

    user_claude = tmp_path / "user-CLAUDE.md"
    user_claude.write_text(
        "<daplug_config>\npreferred_agent: gemini\n</daplug_config>\n"
    )

    project_cfg = config.load_file_config(project_claude)
    user_cfg = config.load_file_config(user_claude)
    value, source = config.resolve_setting("preferred_agent", project_cfg, user_cfg)

    assert value == "codex"
    assert source == "project"


def test_missing_files(tmp_path):
    missing = tmp_path / "missing.md"
    parsed = config.load_file_config(missing)
    assert parsed.format == "none"
    assert parsed.data == {}


def test_malformed_block():
    content = "<daplug_config>\npreferred_agent: codex\n"
    parsed = config.parse_config_content(content)
    assert parsed.has_block
    assert parsed.malformed_block
    assert parsed.data["preferred_agent"] == "codex"


def test_migrate_content_merges():
    content = """
## daplug Settings
preferred_agent: legacy

<daplug_config>
worktree_dir: .worktrees/
preferred_agent: block
</daplug_config>
"""
    new_content, changed, merged = config.migrate_content(content)
    assert changed is True
    assert merged["preferred_agent"] == "block"
    assert merged["worktree_dir"] == ".worktrees/"
    # Legacy line should be removed outside block
    assert re.search(r"^preferred_agent:\s*legacy", new_content, re.MULTILINE) is None
    # Block should still include preferred_agent
    assert "preferred_agent: block" in new_content
