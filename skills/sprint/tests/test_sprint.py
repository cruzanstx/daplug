import importlib.util
import json
import sys
from pathlib import Path


def _load_sprint_module():
    root = Path(__file__).resolve().parents[3]
    sprint_path = root / "skills" / "sprint" / "scripts" / "sprint.py"
    spec = importlib.util.spec_from_file_location("daplug_sprint", sprint_path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    # Ensure dataclasses can resolve string annotations via sys.modules.
    sys.modules["daplug_sprint"] = module
    spec.loader.exec_module(module)
    return module


def test_state_roundtrip(tmp_path):
    m = _load_sprint_module()
    state_file = tmp_path / ".sprint-state.json"
    state = m.SprintState(
        sprint_id="todo-app-2026-01-17",
        created_at="2026-01-17T00:00:00+00:00",
        spec_hash="abc",
        spec_path="inline",
        prompts=[{"id": "001", "status": "pending", "worktree": None, "merged": False, "model": "codex"}],
        current_phase=1,
        total_phases=1,
        model_usage={},
        paused_at=None,
    )
    m.save_state(state, str(state_file))
    loaded = m.load_state(str(state_file))
    assert loaded
    assert loaded.sprint_id == state.sprint_id
    assert loaded.schema_version == m.STATE_SCHEMA_VERSION
    assert loaded.prompts[0]["id"] == "001"


def test_update_prompt_status_sets_timestamps(tmp_path):
    m = _load_sprint_module()
    state = m.SprintState(
        sprint_id="x",
        created_at="2026-01-17T00:00:00+00:00",
        spec_hash="abc",
        spec_path="inline",
        prompts=[{"id": "001", "status": "pending", "worktree": None, "merged": False, "model": "codex"}],
        current_phase=1,
        total_phases=1,
        model_usage={},
        paused_at=None,
    )
    m.update_prompt_status(state, "001", "in_progress")
    p = state.prompts[0]
    assert p["status"] == "in_progress"
    assert p.get("started_at")

    m.update_prompt_status(state, "001", "completed")
    assert p["status"] == "completed"
    assert p.get("finished_at")


def test_parse_prompt_dependencies():
    m = _load_sprint_module()
    text = """# Title

Depends on: 1, 02, 003
"""
    assert m._parse_prompt_dependencies(text) == ["001", "002", "003"]


def test_topo_phases_simple():
    m = _load_sprint_module()
    nodes = ["001", "002", "003"]
    deps = {"001": [], "002": ["001"], "003": ["002"]}
    phases, leftovers = m._topo_phases(nodes, deps)
    assert leftovers == []
    assert phases == [["001"], ["002"], ["003"]]


def test_topo_phases_cycle():
    m = _load_sprint_module()
    nodes = ["001", "002"]
    deps = {"001": ["002"], "002": ["001"]}
    phases, leftovers = m._topo_phases(nodes, deps)
    assert phases == []
    assert leftovers == ["001", "002"]


def test_patch_depends_on_lines(tmp_path):
    m = _load_sprint_module()
    p1 = tmp_path / "001-database.md"
    p2 = tmp_path / "002-auth.md"
    p1.write_text("# Database\n\n## Context\nx\n", encoding="utf-8")
    p2.write_text("# Auth\n\n## Context\nx\n", encoding="utf-8")

    prompts = [
        {"id": "001", "slug": "database", "path": str(p1)},
        {"id": "002", "slug": "auth", "path": str(p2)},
    ]
    deps_by_slug = {"auth": ["database"], "database": []}
    m._patch_prompt_depends_on_lines(prompts, deps_by_slug)

    updated = p2.read_text(encoding="utf-8")
    assert "Depends on: 001" in updated


def test_assign_models_respects_availability(monkeypatch):
    m = _load_sprint_module()
    # Force "claude" to appear unavailable
    monkeypatch.setattr(m, "_cclimits_availability", lambda: {"claude": False, "codex": True, "gemini": True})
    prompts = [{"id": "001", "title": "Auth system", "slug": "auth", "status": "pending"}]
    assigned = m.assign_models(prompts, ["claude", "codex", "gemini"])
    assert assigned["001"] != "claude"
