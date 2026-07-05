"""Tests for --moa (mixture-of-agents) fan-out execution."""

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
EXECUTOR_PATH = SCRIPT_DIR / "executor.py"
EXECUTOR_SPEC = importlib.util.spec_from_file_location("executor", EXECUTOR_PATH)
if EXECUTOR_SPEC is None or EXECUTOR_SPEC.loader is None:
    raise RuntimeError(f"Unable to load executor from {EXECUTOR_PATH}")
executor = importlib.util.module_from_spec(EXECUTOR_SPEC)
sys.modules["executor"] = executor
EXECUTOR_SPEC.loader.exec_module(executor)

import models  # noqa: E402
import worktree as worktree_mod  # noqa: E402


@pytest.fixture()
def no_router(monkeypatch):
    monkeypatch.setattr(models, "_resolve_router_command", lambda *_args, **_kwargs: None)


@pytest.fixture()
def prompt_repo(tmp_path, monkeypatch):
    prompts_dir = tmp_path / "prompts"
    prompts_dir.mkdir()
    prompt_file = prompts_dir / "001-test-prompt.md"
    prompt_file.write_text("# Test Prompt\n\nDo the thing.\n")

    logs_dir = tmp_path / "logs"
    logs_dir.mkdir()

    state_dir = tmp_path / "loop-state"
    state_dir.mkdir()

    monkeypatch.setattr(executor, "get_repo_root", lambda: tmp_path)
    monkeypatch.setattr(executor, "get_cli_logs_dir", lambda _repo_root: logs_dir)
    monkeypatch.setattr(executor, "get_loop_state_dir", lambda: state_dir)
    monkeypatch.setattr(models, "_resolve_router_command", lambda *_args, **_kwargs: None)

    return tmp_path, logs_dir, prompt_file


@pytest.fixture()
def fake_worktrees(tmp_path, monkeypatch):
    """Replace create_worktree with a fake that records calls."""
    calls = []

    def _fake_create_worktree(repo_root, prompt_file, base_branch=None,
                              on_conflict="error", name_suffix=None):
        calls.append({"name_suffix": name_suffix, "on_conflict": on_conflict})
        wt_path = tmp_path / "wt" / (name_suffix or "default")
        wt_path.mkdir(parents=True, exist_ok=True)
        return {
            "worktree_path": str(wt_path),
            "branch_name": f"prompt/001-test-prompt-{name_suffix}" if name_suffix else "prompt/001-test-prompt",
            "task_file": str(wt_path / "TASK.md"),
            "base_branch": "main",
        }

    monkeypatch.setattr(executor, "create_worktree", _fake_create_worktree)
    return calls


# ---------------------------------------------------------------------------
# parse_moa_models validation
# ---------------------------------------------------------------------------

def test_parse_moa_models_valid_list():
    entries = executor.parse_moa_models("codex,qwen36")
    assert [e["model"] for e in entries] == ["codex", "qwen36"]
    assert [e["cli"] for e in entries] == [None, None]
    assert [e["label"] for e in entries] == ["codex", "qwen36"]
    assert [e["spec"] for e in entries] == ["codex", "qwen36"]


def test_parse_moa_models_strips_and_dedupes():
    entries = executor.parse_moa_models(" codex , qwen36 ,codex, ")
    assert [e["label"] for e in entries] == ["codex", "qwen36"]


def test_parse_moa_models_per_entry_cli_override():
    entries = executor.parse_moa_models("codex:opencode,qwen36")
    assert entries[0]["model"] == "codex"
    assert entries[0]["cli"] == "opencode"
    assert entries[0]["label"] == "codex-opencode"
    assert entries[0]["spec"] == "codex:opencode"
    assert entries[1]["cli"] is None


def test_parse_moa_models_cli_aliases_normalize_and_dedupe():
    # cc and claudecode both normalize to claude -> same label -> deduped
    entries = executor.parse_moa_models("cc-sonnet:cc,cc-sonnet:claudecode,codex")
    assert [e["label"] for e in entries] == ["cc-sonnet-claude", "codex"]
    assert entries[0]["cli"] == "claude"


def test_parse_moa_models_same_model_different_clis_are_distinct():
    entries = executor.parse_moa_models("codex,codex:opencode")
    assert [e["label"] for e in entries] == ["codex", "codex-opencode"]


def test_parse_moa_models_rejects_unknown():
    with pytest.raises(ValueError, match="Unknown model in --moa"):
        executor.parse_moa_models("codex,notamodel")


def test_parse_moa_models_rejects_unknown_cli():
    with pytest.raises(ValueError, match="Unknown CLI in --moa entry"):
        executor.parse_moa_models("codex:notacli,qwen36")


def test_parse_moa_models_rejects_unsupported_combo():
    # gemini CLI cannot run the codex model
    with pytest.raises(ValueError, match="--cli gemini is not supported"):
        executor.parse_moa_models("codex:gemini,qwen36")


def test_parse_moa_models_rejects_claude_subagent():
    with pytest.raises(ValueError, match="cc-sonnet, cc-opus, or claude:claude"):
        executor.parse_moa_models("codex,claude")


def test_parse_moa_models_allows_headless_claude_cli():
    entries = executor.parse_moa_models("codex,claude:claude")
    assert entries[1]["model"] == "claude"
    assert entries[1]["cli"] == "claude"
    assert entries[1]["label"] == "claude-claude"


def test_parse_moa_models_requires_two_models():
    with pytest.raises(ValueError, match="at least 2 distinct models"):
        executor.parse_moa_models("codex")
    with pytest.raises(ValueError, match="at least 2 distinct models"):
        executor.parse_moa_models("codex,codex")


# ---------------------------------------------------------------------------
# _moa_cli_info variant handling
# ---------------------------------------------------------------------------

def test_moa_cli_info_keeps_supported_variant(no_router, tmp_path):
    info, variant, dropped = executor._moa_cli_info("codex", tmp_path, "high")
    assert variant == "high"
    assert dropped is False
    assert 'model_reasoning_effort="high"' in " ".join(info["command"])


def test_moa_cli_info_drops_unsupported_variant(no_router, tmp_path):
    # Codex only supports high/xhigh; 'low' raises and should fall back.
    info, variant, dropped = executor._moa_cli_info("codex", tmp_path, "low")
    assert variant is None
    assert dropped is True
    assert "model_reasoning_effort" not in " ".join(info["command"])


def test_moa_cli_info_no_variant(no_router, tmp_path):
    _info, variant, dropped = executor._moa_cli_info("qwen36", tmp_path, None)
    assert variant is None
    assert dropped is False


# ---------------------------------------------------------------------------
# Argparse-level mutual exclusion
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("argv", [
    ["executor.py", "001", "--moa", "codex,qwen36", "--model", "codex"],
    ["executor.py", "001", "--moa", "codex,qwen36", "--cli", "opencode"],
    ["executor.py", "001", "--moa", "codex"],
    ["executor.py", "001", "--moa", "codex,claude"],
    ["executor.py", "001", "--moa", "codex,qwen36", "--loop-status"],
])
def test_main_rejects_invalid_moa_combinations(prompt_repo, monkeypatch, argv):
    monkeypatch.setattr(sys, "argv", argv)
    with pytest.raises(SystemExit) as excinfo:
        executor.main()
    assert excinfo.value.code == 2


# ---------------------------------------------------------------------------
# main() fan-out
# ---------------------------------------------------------------------------

def test_moa_info_mode_creates_worktree_per_model(prompt_repo, fake_worktrees, monkeypatch, capsys):
    repo_root, _logs_dir, _prompt_file = prompt_repo
    monkeypatch.setattr(sys, "argv", ["executor.py", "001", "--moa", "codex,qwen36"])

    executor.main()
    output = json.loads(capsys.readouterr().out)

    assert output["model"] == "moa"
    assert output["moa_models"] == ["codex", "qwen36"]
    assert output["cli_command"] is None

    moa = output["prompts"][0]["moa"]
    assert moa["models"] == ["codex", "qwen36"]
    assert [r["model"] for r in moa["runs"]] == ["codex", "qwen36"]
    assert all(r["status"] == "info" for r in moa["runs"])
    assert [c["name_suffix"] for c in fake_worktrees] == ["moa-codex", "moa-qwen36"]

    # Manifest is persisted under <loop-state>/moa/
    manifest_path = Path(moa["manifest_file"])
    assert manifest_path.exists()
    manifest = json.loads(manifest_path.read_text())
    assert manifest["prompt_number"] == "001"
    assert manifest["launched"] is False


def test_moa_run_launches_each_model(prompt_repo, fake_worktrees, monkeypatch, capsys):
    repo_root, _logs_dir, _prompt_file = prompt_repo
    run_calls = []

    def _fake_run_cli(cli_info, content, cwd, log_file, sandbox_config=None):
        run_calls.append({"cwd": cwd, "log": str(log_file)})
        return {"status": "running", "pid": 4242, "log": str(log_file)}

    monkeypatch.setattr(executor, "run_cli", _fake_run_cli)
    monkeypatch.setattr(sys, "argv", ["executor.py", "001", "--moa", "codex,qwen36", "--run"])

    executor.main()
    output = json.loads(capsys.readouterr().out)

    moa = output["prompts"][0]["moa"]
    assert all(r["status"] == "running" for r in moa["runs"])
    assert len(run_calls) == 2
    assert run_calls[0]["cwd"] != run_calls[1]["cwd"]
    # Per-model logs must not collide
    assert run_calls[0]["log"] != run_calls[1]["log"]


def test_moa_run_loop_uses_per_model_state_keys(prompt_repo, fake_worktrees, monkeypatch, capsys):
    repo_root, _logs_dir, _prompt_file = prompt_repo
    loop_calls = []

    def _fake_loop_background(**kwargs):
        loop_calls.append(kwargs)
        return {
            "status": "loop_running",
            "pid": 555,
            "loop_log": f"/tmp/{kwargs['prompt_number']}-loop.log",
            "state_file": f"/tmp/{kwargs['prompt_number']}.json",
            "max_iterations": kwargs["max_iterations"],
            "completion_marker": kwargs["completion_marker"],
        }

    monkeypatch.setattr(executor, "run_verification_loop_background", _fake_loop_background)
    monkeypatch.setattr(sys, "argv", ["executor.py", "001", "--moa", "codex,qwen36", "--run", "--loop"])

    executor.main()
    output = json.loads(capsys.readouterr().out)

    assert [c["prompt_number"] for c in loop_calls] == ["001-moa-codex", "001-moa-qwen36"]
    assert all(c["cli_override"] is None for c in loop_calls)
    assert [c["model"] for c in loop_calls] == ["codex", "qwen36"]

    moa = output["prompts"][0]["moa"]
    assert all(r["status"] == "loop_running" for r in moa["runs"])
    assert moa["runs"][0]["state_file"] == "/tmp/001-moa-codex.json"


def test_moa_per_entry_cli_override_end_to_end(prompt_repo, fake_worktrees, monkeypatch, capsys):
    repo_root, _logs_dir, _prompt_file = prompt_repo
    loop_calls = []

    def _fake_loop_background(**kwargs):
        loop_calls.append(kwargs)
        return {
            "status": "loop_running",
            "pid": 555,
            "loop_log": f"/tmp/{kwargs['prompt_number']}-loop.log",
            "state_file": f"/tmp/{kwargs['prompt_number']}.json",
            "max_iterations": kwargs["max_iterations"],
            "completion_marker": kwargs["completion_marker"],
        }

    monkeypatch.setattr(executor, "run_verification_loop_background", _fake_loop_background)
    monkeypatch.setattr(
        sys, "argv",
        ["executor.py", "001", "--moa", "codex:opencode,qwen36", "--run", "--loop"],
    )

    executor.main()
    output = json.loads(capsys.readouterr().out)

    assert output["moa_models"] == ["codex:opencode", "qwen36"]

    # Loop re-invocations must carry the per-entry override and label-keyed state
    assert [c["prompt_number"] for c in loop_calls] == ["001-moa-codex-opencode", "001-moa-qwen36"]
    assert [c["cli_override"] for c in loop_calls] == ["opencode", None]
    # The overridden run's resolved command is an OpenCode invocation
    assert loop_calls[0]["cli_info"]["command"][0] == "opencode"

    # Worktrees are suffixed by label so codex and codex:opencode never collide
    assert [c["name_suffix"] for c in fake_worktrees] == ["moa-codex-opencode", "moa-qwen36"]

    runs = output["prompts"][0]["moa"]["runs"]
    assert runs[0]["cli"] == "opencode"
    assert runs[0]["label"] == "codex-opencode"


def test_moa_conflict_recorded_per_run(prompt_repo, monkeypatch, capsys):
    repo_root, _logs_dir, _prompt_file = prompt_repo

    def _conflict_worktree(repo_root, prompt_file, base_branch=None,
                           on_conflict="error", name_suffix=None):
        return {
            "conflict": True,
            "conflict_type": "worktree_exists",
            "existing_worktree": "/somewhere",
            "branch_name": f"prompt/001-test-prompt-{name_suffix}",
            "options": ["remove", "reuse", "increment"],
            "message": "exists",
        }

    monkeypatch.setattr(executor, "create_worktree", _conflict_worktree)
    monkeypatch.setattr(sys, "argv", ["executor.py", "001", "--moa", "codex,qwen36", "--run"])

    executor.main()
    output = json.loads(capsys.readouterr().out)

    moa = output["prompts"][0]["moa"]
    assert all(r["status"] == "conflict" for r in moa["runs"])
    assert all("execution" not in r for r in moa["runs"])


def test_moa_per_model_failure_does_not_abort_fanout(prompt_repo, monkeypatch, capsys):
    repo_root, _logs_dir, _prompt_file = prompt_repo
    created = []

    def _flaky_worktree(repo_root, prompt_file, base_branch=None,
                        on_conflict="error", name_suffix=None):
        if name_suffix == "moa-codex":
            raise RuntimeError("boom")
        wt = repo_root / "wt" / (name_suffix or "x")
        wt.mkdir(parents=True, exist_ok=True)
        created.append(name_suffix)
        return {"worktree_path": str(wt), "branch_name": f"b/{name_suffix}",
                "task_file": str(wt / "TASK.md"), "base_branch": "main"}

    monkeypatch.setattr(executor, "create_worktree", _flaky_worktree)
    monkeypatch.setattr(
        executor, "run_cli",
        lambda cli_info, content, cwd, log_file, sandbox_config=None:
            {"status": "running", "pid": 1, "log": str(log_file)},
    )
    monkeypatch.setattr(sys, "argv", ["executor.py", "001", "--moa", "codex,qwen36", "--run"])

    executor.main()
    output = json.loads(capsys.readouterr().out)

    runs = output["prompts"][0]["moa"]["runs"]
    assert runs[0]["status"] == "error"
    assert "boom" in runs[0]["error"]
    assert runs[1]["status"] == "running"
    assert created == ["moa-qwen36"]


# ---------------------------------------------------------------------------
# create_worktree name_suffix (real git)
# ---------------------------------------------------------------------------

def test_create_worktree_name_suffix(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=repo, check=True)
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t",
                    "commit", "--allow-empty", "-qm", "init"], cwd=repo, check=True)
    prompts_dir = repo / "prompts"
    prompts_dir.mkdir()
    prompt_file = prompts_dir / "007-suffix-test.md"
    prompt_file.write_text("# Suffix test\n")

    worktrees_dir = tmp_path / "worktrees"
    monkeypatch.setattr(worktree_mod, "get_worktree_dir", lambda _repo_root: worktrees_dir)
    monkeypatch.setattr(worktree_mod, "install_worktree_dependencies",
                        lambda _path: {"installed": [], "errors": []})

    info = worktree_mod.create_worktree(repo, prompt_file, base_branch="main",
                                        name_suffix="moa-codex")
    assert info["branch_name"] == "prompt/007-suffix-test-moa-codex"
    assert "-moa-codex-" in Path(info["worktree_path"]).name
    assert Path(info["worktree_path"]).exists()

    # A second model's worktree for the same prompt must not conflict
    info2 = worktree_mod.create_worktree(repo, prompt_file, base_branch="main",
                                         name_suffix="moa-qwen36")
    assert info2["branch_name"] == "prompt/007-suffix-test-moa-qwen36"
