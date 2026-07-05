#!/usr/bin/env python3
"""Tests for the model registry generator."""

from __future__ import annotations

import importlib.util
import shutil
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = REPO_ROOT / "scripts" / "manage-models.py"
spec = importlib.util.spec_from_file_location("manage_models", MODULE_PATH)
if spec is None or spec.loader is None:
    raise RuntimeError(f"Unable to load manage-models from {MODULE_PATH}")
manage_models = importlib.util.module_from_spec(spec)
spec.loader.exec_module(manage_models)


def copy_model_targets(tmp_path: Path) -> Path:
    root = tmp_path / "plugin"
    for relative, _updater in manage_models.TARGETS:
        source = REPO_ROOT / relative
        dest = root / relative
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, dest)
    scripts_dir = root / "scripts"
    scripts_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(REPO_ROOT / "scripts" / "models.json", scripts_dir / "models.json")
    return root


def test_models_json_loads_and_has_required_fields():
    registry = manage_models.load_registry(REPO_ROOT)
    assert registry["schema_version"] == 1
    assert len(registry["models"]) == 41
    for model in registry["models"]:
        assert manage_models.REQUIRED_MODEL_FIELDS <= set(model)
        assert manage_models.REQUIRED_DOC_FIELDS <= set(model["docs"])
        assert isinstance(model["command"], list)
        assert all(isinstance(item, str) for item in model["command"])
        assert isinstance(model["env"], dict)
        assert all(isinstance(key, str) and isinstance(value, str) for key, value in model["env"].items())
        assert model["stdin_mode"] in manage_models.ALLOWED_STDIN_MODES


def test_default_command_builder_matches_registry_commands():
    registry = manage_models.load_registry(REPO_ROOT)
    for model in registry["models"]:
        command = manage_models.default_command(
            model["default_cli"],
            model["model_id"],
            model["codex_profile"],
            model["claude_model_flag"],
            model["default_variant"],
        )
        assert command == model["command"], model["name"]
        assert manage_models.command_env(model["default_cli"], command) == model["env"], model["name"]
        assert manage_models.stdin_mode_for_cli(model["default_cli"]) == model["stdin_mode"], model["name"]


def test_generate_is_idempotent_on_temp_copy(tmp_path: Path):
    root = copy_model_targets(tmp_path)
    manage_models.generate_models(root, write=True)
    before = {path: path.read_text() for path, _new in manage_models.render_all(root).items()}
    changed = manage_models.generate_models(root, write=True)
    after = {path: path.read_text() for path in before}
    assert changed == []
    assert after == before


def test_check_detects_and_repairs_generated_drift(tmp_path: Path):
    root = copy_model_targets(tmp_path)
    manage_models.generate_models(root, write=True)
    assert manage_models.check_models(root) is True

    run_prompt = root / "commands" / "run-prompt.md"
    run_prompt.write_text(run_prompt.read_text().replace("synthetic, ", "", 1))

    assert manage_models.check_models(root) is False
    manage_models.generate_models(root, write=True)
    assert manage_models.check_models(root) is True


def test_load_registry_rejects_missing_model_fields(tmp_path: Path):
    root = copy_model_targets(tmp_path)
    registry_path = root / "scripts" / "models.json"
    registry = manage_models.load_registry(root)
    del registry["models"][0]["display"]
    import json
    registry_path.write_text(json.dumps(registry))

    with pytest.raises(manage_models.RegistryError, match="missing fields: display"):
        manage_models.load_registry(root)
