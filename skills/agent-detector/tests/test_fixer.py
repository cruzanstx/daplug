import json
import sys
import time
from pathlib import Path

import pytest

SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.append(str(SCRIPT_DIR))

from fixer import (  # noqa: E402
    apply_fix_safely,
    backup_config,
    deep_merge_defaults,
    deep_merge_overwrite,
)
from plugins.base import ConfigIssue  # noqa: E402
from plugins.codex import CodexCLI  # noqa: E402


def test_backup_config_creates_timestamped_backup(tmp_path: Path):
    cfg = tmp_path / "config.json"
    cfg.write_text('{"a": 1}\n', encoding="utf-8")

    backup = backup_config(cfg)
    assert backup.exists()
    assert backup.name.startswith("config.json.bak.")
    assert backup.read_text(encoding="utf-8") == cfg.read_text(encoding="utf-8")


def test_backup_config_rotates_to_three(tmp_path: Path):
    cfg = tmp_path / "config.json"
    cfg.write_text('{"a": 1}\n', encoding="utf-8")

    for i in range(4):
        cfg.write_text(json.dumps({"i": i}) + "\n", encoding="utf-8")
        backup_config(cfg)
        time.sleep(0.01)

    backups = sorted(tmp_path.glob("config.json.bak.*"))
    assert len(backups) == 3


def test_deep_merge_defaults_preserves_user_values():
    target = {"a": 1, "nested": {"x": "keep"}}
    defaults = {"a": 2, "b": 3, "nested": {"x": "default", "y": "add"}}
    merged = deep_merge_defaults(target, defaults)
    assert merged["a"] == 1
    assert merged["b"] == 3
    assert merged["nested"]["x"] == "keep"
    assert merged["nested"]["y"] == "add"


def test_deep_merge_overwrite_overrides_patch_keys():
    target = {"a": 1, "nested": {"x": "keep", "y": "old"}}
    patch = {"a": 2, "nested": {"y": "new"}}
    merged = deep_merge_overwrite(target, patch)
    assert merged["a"] == 2
    assert merged["nested"]["x"] == "keep"
    assert merged["nested"]["y"] == "new"


def test_apply_fix_safely_rolls_back_on_validation_failure(tmp_path: Path):
    cfg = tmp_path / "bad.json"
    cfg.write_text("{}\n", encoding="utf-8")

    class DummyPlugin:
        name = "dummy"

        def get_config_paths(self):
            return [cfg]

        def detect_issues(self):
            try:
                json.loads(cfg.read_text(encoding="utf-8"))
                return []
            except json.JSONDecodeError:
                return [
                    ConfigIssue(
                        type="invalid_json",
                        severity="error",
                        message="bad",
                        fix_available=True,
                        config_path=str(cfg),
                    )
                ]

        def apply_fix(self, issue: ConfigIssue) -> bool:
            _ = issue
            cfg.write_text("{\n", encoding="utf-8")
            return True

    plugin = DummyPlugin()
    issue = ConfigIssue(
        type="invalid_json",
        severity="error",
        message="bad",
        fix_available=True,
        config_path=str(cfg),
    )
    result = apply_fix_safely(plugin, issue)
    assert result.success is False
    assert cfg.read_text(encoding="utf-8") == "{}\n"


def test_templates_are_valid_json_or_yaml():
    templates_dir = Path(__file__).resolve().parents[1] / "templates"
    assert templates_dir.exists()

    import yaml

    for path in templates_dir.iterdir():
        if not path.is_file():
            continue
        if path.suffix.lower() in {".json", ".jsonc"}:
            json.loads(path.read_text(encoding="utf-8"))
        elif path.suffix.lower() in {".yml", ".yaml"}:
            yaml.safe_load(path.read_text(encoding="utf-8"))


def _codex_plugin_for_path(monkeypatch, config_path: Path) -> CodexCLI:
    plugin = CodexCLI()
    monkeypatch.setattr(plugin, "detect_installation", lambda: (True, "/usr/local/bin/codex"))
    monkeypatch.setenv("OPENAI_API_KEY", "test")
    setattr(plugin, "_config_paths", [config_path])
    return plugin


def test_codex_outdated_config_fix_merges_without_clobber(tmp_path: Path, monkeypatch):
    cfg = tmp_path / "codex.json"
    cfg.write_text(
        json.dumps({"model": "my-custom-model", "notify": {"on_complete": True}, "custom": {"keep": True}})
        + "\n",
        encoding="utf-8",
    )
    plugin = _codex_plugin_for_path(monkeypatch, cfg)

    issue = next(i for i in plugin.detect_issues() if i.type == "outdated_config")
    result = apply_fix_safely(plugin, issue)
    assert result.success is True

    updated = json.loads(cfg.read_text(encoding="utf-8"))
    assert updated["model"] == "my-custom-model"
    assert updated["notify"]["on_complete"] is True
    assert updated["notify"]["command"] == ""
    assert updated["custom"]["keep"] is True
    assert updated["approval_mode"] == "full-auto"
    assert updated["full_auto"] is True


def test_codex_invalid_json_fix_replaces_with_template(tmp_path: Path, monkeypatch):
    cfg = tmp_path / "codex.json"
    cfg.write_text("{\n", encoding="utf-8")
    plugin = _codex_plugin_for_path(monkeypatch, cfg)

    issue = next(i for i in plugin.detect_issues() if i.type == "invalid_json")
    result = apply_fix_safely(plugin, issue)
    assert result.success is True

    updated = json.loads(cfg.read_text(encoding="utf-8"))
    assert updated["model"] == "gpt-5.2-codex"
    assert updated["approval_mode"] == "full-auto"

