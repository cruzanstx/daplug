import importlib.util
import json
import sys
from pathlib import Path

import pytest


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


def test_parse_prompt_range():
    m = _load_sprint_module()
    assert m.parse_prompt_range("001-003,010,2") == ["001", "002", "003", "010"]
    assert m.parse_prompt_range(None) == []
    with pytest.raises(ValueError):
        m.parse_prompt_range("x")


def test_discover_existing_prompts_filters(tmp_path):
    m = _load_sprint_module()
    prompts_dir = tmp_path / "prompts"
    prompts_dir.mkdir()
    (prompts_dir / "001-one.md").write_text("# One\n", encoding="utf-8")
    (prompts_dir / "002-two.md").write_text("# Two\n", encoding="utf-8")
    sub = prompts_dir / "providers"
    sub.mkdir()
    (sub / "003-three.md").write_text("# Three\n", encoding="utf-8")
    # Non-prompt markdown should be ignored
    (prompts_dir / "README.md").write_text("ignore", encoding="utf-8")

    all_prompts = m.discover_existing_prompts(prompts_dir)
    assert [p["number"] for p in all_prompts] == ["001", "002", "003"]
    assert all_prompts[2]["folder"] == "providers"

    included = m.discover_existing_prompts(prompts_dir, include="001-002")
    assert [p["number"] for p in included] == ["001", "002"]

    excluded = m.discover_existing_prompts(prompts_dir, exclude="002")
    assert [p["number"] for p in excluded] == ["001", "003"]

    folder_only = m.discover_existing_prompts(prompts_dir, folder="providers/")
    assert [p["number"] for p in folder_only] == ["003"]
    assert folder_only[0]["folder"] == "providers"


def test_analyze_prompt_content_extracts_fields():
    m = _load_sprint_module()
    prompt = {
        "name": "001-test.md",
        "content": """
<objective>
Add a --from-existing flag
</objective>

Depends on: 2

@skills/sprint/scripts/sprint.py

<output>
- `skills/sprint/scripts/sprint.py`
</output>

<verification>
python3 -m pytest -q
</verification>
""",
    }
    analysis = m.analyze_prompt_content(prompt)
    assert analysis["title"] == "Add a --from-existing flag"
    assert "002" in analysis["dependencies"]
    assert "skills/sprint/scripts/sprint.py" in analysis["referenced_files"]
    assert "skills/sprint/scripts/sprint.py" in analysis["output_files"]
    assert "python3 -m pytest -q" in analysis["verification_commands"]


def test_from_existing_mutual_exclusion_errors():
    m = _load_sprint_module()
    with pytest.raises(SystemExit) as exc:
        m._dispatch(["sprint.py", "--from-existing", "some-spec"])
    assert exc.value.code == 2


def test_from_existing_dry_run_dispatch(tmp_path):
    m = _load_sprint_module()
    prompts_dir = tmp_path / "prompts"
    prompts_dir.mkdir()
    (prompts_dir / "001-one.md").write_text("# One\n", encoding="utf-8")
    rc = m._dispatch(
        ["sprint.py", "--from-existing", "--dry-run", "--output-dir", str(prompts_dir), "--models", "codex"]
    )
    assert rc == 0
