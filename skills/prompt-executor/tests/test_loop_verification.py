"""Tests for --require-diff and dead-loop detection in run_verification_loop.

Follows the monkeypatched-loop style from test_worktree_isolation.py:
real git repos as execution cwd, fake run_cli_foreground, isolated state/log dirs.
"""
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
EXECUTOR_PATH = SCRIPT_DIR / "executor.py"
_executor_spec = importlib.util.spec_from_file_location("executor", EXECUTOR_PATH)
if _executor_spec is None or _executor_spec.loader is None:
    raise ImportError(f"Unable to load executor from {EXECUTOR_PATH}")
executor = importlib.util.module_from_spec(_executor_spec)
sys.modules["executor"] = executor
_executor_spec.loader.exec_module(executor)

import loop  # noqa: E402  -- needed so monkeypatch can target loop's namespace


def _run(cmd, cwd):
    subprocess.run(cmd, cwd=cwd, check=True, capture_output=True)


def _init_repo(path: Path, initial_branch: str = "main") -> Path:
    path.mkdir(parents=True, exist_ok=True)
    _run(["git", "init", "-b", initial_branch], cwd=path)
    _run(["git", "config", "user.email", "t@t"], cwd=path)
    _run(["git", "config", "user.name", "t"], cwd=path)
    (path / "README.md").write_text("seed\n")
    _run(["git", "add", "."], cwd=path)
    _run(["git", "commit", "-m", "seed"], cwd=path)
    return path


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def loop_env(tmp_path, monkeypatch):
    """Real git repo as execution cwd + isolated state/log dirs."""
    repo = _init_repo(tmp_path / "repo")
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    state_dir = tmp_path / "loop-state"
    state_dir.mkdir()

    monkeypatch.setattr(loop, "get_loop_state_dir", lambda: state_dir)

    cli_info = {
        "command": ["fake-cli", "exec"],
        "env": {},
        "stdin_mode": "dash",
        "display": "fake",
    }
    return {
        "repo": repo,
        "log_dir": log_dir,
        "state_dir": state_dir,
        "cli_info": cli_info,
    }


def _make_cli(
    *,
    write_marker: bool = True,
    retry_reason: str | None = None,
    create_files: dict[str, str] | None = None,
    git_commit: bool = False,
    marker: str = "VERIFICATION_COMPLETE",
):
    """Build a stand-in for run_cli_foreground.

    write_marker: emit a completion marker in the log file
    retry_reason: emit a NEEDS_RETRY marker (takes precedence over write_marker)
    create_files: {relative_path: content} to create in the execution cwd
    git_commit: stage and commit all changes in the execution cwd
    """
    def fake_run(cli_info, content, cwd, log_file, sandbox_config=None):
        with open(log_file, "w") as f:
            f.write(content)
            f.write("\n--- model output ---\n")
            if retry_reason:
                f.write(f"<verification>NEEDS_RETRY: {retry_reason}</verification>\n")
            elif write_marker:
                f.write(f"<verification>{marker}</verification>\n")
        if create_files:
            for rel_path, file_content in create_files.items():
                p = Path(cwd) / rel_path
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text(file_content)
        if git_commit:
            _run(["git", "add", "-A"], cwd=cwd)
            _run(["git", "commit", "-m", "agent work"], cwd=cwd)
        return {"status": "ok", "exit_code": 0}
    return fake_run


def _make_seq_cli(*, calls: list[dict]):
    """Build a fake CLI that returns different results on successive calls.

    Each call dict supports: write_marker, retry_reason, create_files, git_commit.
    """
    call_count = [0]

    def fake_run(cli_info, content, cwd, log_file, sandbox_config=None):
        idx = min(call_count[0], len(calls) - 1)
        call = calls[idx]
        call_count[0] += 1
        with open(log_file, "w") as f:
            f.write(content)
            f.write("\n--- model output ---\n")
            if call.get("retry_reason"):
                f.write(f"<verification>NEEDS_RETRY: {call['retry_reason']}</verification>\n")
            elif call.get("write_marker", True):
                f.write("<verification>VERIFICATION_COMPLETE</verification>\n")
        if call.get("create_files"):
            for rel_path, file_content in call["create_files"].items():
                p = Path(cwd) / rel_path
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text(file_content)
        if call.get("git_commit"):
            _run(["git", "add", "-A"], cwd=cwd)
            _run(["git", "commit", "-m", "agent work"], cwd=cwd)
        return {"status": "ok", "exit_code": 0}
    return fake_run


def _call_loop(
    env,
    *,
    monkeypatch,
    fake_cli,
    max_iterations=2,
    require_diff=False,
):
    monkeypatch.setattr(loop, "run_cli_foreground", fake_cli)
    return executor.run_verification_loop(
        cli_info=env["cli_info"],
        original_content="do the thing",
        cwd=str(env["repo"]),
        log_dir=env["log_dir"],
        prompt_number="999",
        model="fake",
        max_iterations=max_iterations,
        completion_marker="VERIFICATION_COMPLETE",
        execution_timestamp="20260703-000000",
        require_diff=require_diff,
    )


# ---------------------------------------------------------------------------
# --require-diff: marker + no changes → completed_unverified
# ---------------------------------------------------------------------------

def test_require_diff_marker_no_changes_final_iteration_completed_unverified(loop_env, monkeypatch):
    """Marker found but no file changes on the final iteration → completed_unverified."""
    fake_cli = _make_cli(write_marker=True)
    result = _call_loop(
        loop_env, monkeypatch=monkeypatch, fake_cli=fake_cli,
        max_iterations=1, require_diff=True,
    )
    assert result["final_status"] == "completed_unverified"
    assert result["status"] == "completed_unverified"
    assert len(result["iterations"]) == 1
    assert result["iterations"][0]["marker_found"] is False
    assert "no file changes" in result["iterations"][0]["retry_reason"]

    state = json.loads(Path(result["state_file"]).read_text())
    assert state["status"] == "completed_unverified"


def test_require_diff_marker_no_changes_continues_with_synthetic_retry(loop_env, monkeypatch):
    """Marker found but no file changes → loop continues with synthetic retry_reason."""
    fake_cli = _make_cli(write_marker=True)
    result = _call_loop(
        loop_env, monkeypatch=monkeypatch, fake_cli=fake_cli,
        max_iterations=2, require_diff=True,
    )
    # Two iterations ran (first rejected, second also rejected)
    assert len(result["iterations"]) == 2
    assert result["iterations"][0]["marker_found"] is False
    assert "no file changes" in result["iterations"][0]["retry_reason"]
    # Second iteration has the same synthetic reason → stalled
    assert result["final_status"] == "stalled"


# ---------------------------------------------------------------------------
# --require-diff: marker + real file change → completed
# ---------------------------------------------------------------------------

def test_require_diff_marker_real_file_change_completed(loop_env, monkeypatch):
    """Marker found AND a real file was created → completed."""
    fake_cli = _make_cli(write_marker=True, create_files={"new_module.py": "x = 1\n"})
    result = _call_loop(
        loop_env, monkeypatch=monkeypatch, fake_cli=fake_cli,
        max_iterations=1, require_diff=True,
    )
    assert result["final_status"] == "completed"
    assert result["status"] == "completed"
    assert result["iterations"][0]["marker_found"] is True


def test_require_diff_marker_modified_tracked_file_completed(loop_env, monkeypatch):
    """Marker found AND a tracked file was modified → completed."""
    fake_cli = _make_cli(write_marker=True, create_files={"README.md": "changed\n"})
    result = _call_loop(
        loop_env, monkeypatch=monkeypatch, fake_cli=fake_cli,
        max_iterations=1, require_diff=True,
    )
    assert result["final_status"] == "completed"


# ---------------------------------------------------------------------------
# --require-diff: marker + committed-but-clean worktree → completed
# ---------------------------------------------------------------------------

def test_require_diff_marker_committed_but_clean_completed(loop_env, monkeypatch):
    """Marker found AND agent committed its work → completed (commits count)."""
    fake_cli = _make_cli(
        write_marker=True,
        create_files={"new_feature.py": "pass\n"},
        git_commit=True,
    )
    result = _call_loop(
        loop_env, monkeypatch=monkeypatch, fake_cli=fake_cli,
        max_iterations=1, require_diff=True,
    )
    assert result["final_status"] == "completed"
    assert result["status"] == "completed"


# ---------------------------------------------------------------------------
# --require-diff: TASK.md / .sisyphus/ only changes do NOT count
# ---------------------------------------------------------------------------

def test_require_diff_task_md_only_does_not_count(loop_env, monkeypatch):
    """TASK.md is an executor artifact — creating it alone should not count as a change."""
    fake_cli = _make_cli(write_marker=True, create_files={"TASK.md": "task body\n"})
    result = _call_loop(
        loop_env, monkeypatch=monkeypatch, fake_cli=fake_cli,
        max_iterations=1, require_diff=True,
    )
    assert result["final_status"] == "completed_unverified"


def test_require_diff_sisyphus_only_does_not_count(loop_env, monkeypatch):
    """.sisyphus/ files are executor artifacts — creating them alone should not count."""
    fake_cli = _make_cli(
        write_marker=True,
        create_files={".sisyphus/plan.md": "plan\n"},
    )
    result = _call_loop(
        loop_env, monkeypatch=monkeypatch, fake_cli=fake_cli,
        max_iterations=1, require_diff=True,
    )
    assert result["final_status"] == "completed_unverified"


def test_require_diff_real_file_alongside_task_md_counts(loop_env, monkeypatch):
    """If the agent creates both TASK.md and a real file, the real file counts."""
    fake_cli = _make_cli(
        write_marker=True,
        create_files={"TASK.md": "task\n", "src/main.py": "print('hello')\n"},
    )
    result = _call_loop(
        env=loop_env, monkeypatch=monkeypatch, fake_cli=fake_cli,
        max_iterations=1, require_diff=True,
    )
    assert result["final_status"] == "completed"


# ---------------------------------------------------------------------------
# Dead-loop: two identical consecutive retry_reasons → stalled
# ---------------------------------------------------------------------------

def test_stalled_two_identical_retry_reasons(loop_env, monkeypatch):
    """Two consecutive iterations with the same retry_reason → stalled."""
    fake_cli = _make_seq_cli(calls=[
        {"write_marker": False, "retry_reason": "tests failing"},
        {"write_marker": False, "retry_reason": "tests failing"},
    ])
    result = _call_loop(
        loop_env, monkeypatch=monkeypatch, fake_cli=fake_cli,
        max_iterations=5,
    )
    assert result["final_status"] == "stalled"
    assert result["status"] == "stalled"
    assert "no progress" in result.get("failure_reason", "").lower()
    assert len(result["iterations"]) == 2

    state = json.loads(Path(result["state_file"]).read_text())
    assert state["status"] == "stalled"


def test_stalled_case_insensitive_comparison(loop_env, monkeypatch):
    """Stalled detection is case/whitespace-insensitive."""
    fake_cli = _make_seq_cli(calls=[
        {"write_marker": False, "retry_reason": "  Tests   Failing  "},
        {"write_marker": False, "retry_reason": "tests failing"},
    ])
    result = _call_loop(
        loop_env, monkeypatch=monkeypatch, fake_cli=fake_cli,
        max_iterations=5,
    )
    assert result["final_status"] == "stalled"


# ---------------------------------------------------------------------------
# Dead-loop: isolation-refusal retry_reason → blocked (first occurrence)
# ---------------------------------------------------------------------------

def test_blocked_isolation_boundary_refusal(loop_env, monkeypatch):
    """Retry reason referencing the isolation boundary → blocked after first iteration."""
    fake_cli = _make_cli(
        write_marker=False,
        retry_reason="cannot read /storage/projects/original/config.yaml: outside the isolated worktree",
    )
    result = _call_loop(
        loop_env, monkeypatch=monkeypatch, fake_cli=fake_cli,
        max_iterations=5,
    )
    assert result["final_status"] == "blocked"
    assert result["status"] == "blocked"
    assert len(result["iterations"]) == 1  # aborted after first occurrence

    state = json.loads(Path(result["state_file"]).read_text())
    assert state["status"] == "blocked"
    assert state.get("failure_reason")

    # Suggested next step present
    steps = state.get("suggested_next_steps", [])
    assert any("without --worktree" in s.get("text", "") for s in steps)


def test_blocked_cannot_read_outside_path(loop_env, monkeypatch):
    """"cannot read" + absolute path not under cwd → blocked."""
    fake_cli = _make_cli(
        write_marker=False,
        retry_reason="cannot read /etc/passwd for configuration",
    )
    result = _call_loop(
        loop_env, monkeypatch=monkeypatch, fake_cli=fake_cli,
        max_iterations=5,
    )
    assert result["final_status"] == "blocked"


def test_blocked_isolation_boundary_phrase(loop_env, monkeypatch):
    """Explicit 'isolation boundary' phrase → blocked."""
    fake_cli = _make_cli(
        write_marker=False,
        retry_reason="file is beyond the isolation boundary",
    )
    result = _call_loop(
        loop_env, monkeypatch=monkeypatch, fake_cli=fake_cli,
        max_iterations=5,
    )
    assert result["final_status"] == "blocked"


# ---------------------------------------------------------------------------
# No flag, varying retry reasons → existing behavior unchanged
# ---------------------------------------------------------------------------

def test_no_flag_varying_retry_reasons_no_stall(loop_env, monkeypatch):
    """Without --require-diff, varying retry reasons do not stall."""
    fake_cli = _make_seq_cli(calls=[
        {"write_marker": False, "retry_reason": "tests failing"},
        {"write_marker": False, "retry_reason": "lint errors remain"},
        {"write_marker": False, "retry_reason": "build broken"},
    ])
    result = _call_loop(
        loop_env, monkeypatch=monkeypatch, fake_cli=fake_cli,
        max_iterations=3,
    )
    assert result["final_status"] == "max_iterations_reached"
    assert len(result["iterations"]) == 3


def test_no_flag_marker_no_diff_still_completes(loop_env, monkeypatch):
    """Without --require-diff, marker found with no changes still completes (issue #14 old behavior)."""
    fake_cli = _make_cli(write_marker=True)
    result = _call_loop(
        loop_env, monkeypatch=monkeypatch, fake_cli=fake_cli,
        max_iterations=1, require_diff=False,
    )
    assert result["final_status"] == "completed"
    assert result["status"] == "completed"


# ---------------------------------------------------------------------------
# --require-diff survives background re-entry round trip
# ---------------------------------------------------------------------------

class _FakePopen:
    """Captures the spawned command."""
    captured_cmd = None
    captured_cwd = None

    def __init__(self, cmd, cwd=None, **_kwargs):
        type(self).captured_cmd = list(cmd)
        type(self).captured_cwd = cwd
        self.pid = 4242


def test_require_diff_forwarded_in_background_reentry(tmp_path, monkeypatch):
    """--require-diff must survive the background→foreground round trip."""
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    state_dir = tmp_path / "state"
    state_dir.mkdir()

    worktree = tmp_path / "worktree"
    worktree.mkdir()
    (worktree / "TASK.md").write_text("body\n")

    monkeypatch.setattr(loop, "get_loop_state_dir", lambda: state_dir)
    _FakePopen.captured_cmd = None
    monkeypatch.setattr(executor.subprocess, "Popen", _FakePopen)

    executor.run_verification_loop_background(
        cli_info={"command": ["fake"], "env": {}, "stdin_mode": "dash", "display": "fake"},
        original_content="body",
        cwd=str(worktree),
        log_dir=log_dir,
        prompt_number="999",
        model="fake",
        max_iterations=3,
        completion_marker="VERIFICATION_COMPLETE",
        execution_timestamp="20260703-000000",
        worktree_path=str(worktree),
        branch_name="prompt/999-test",
        original_repo_root=str(tmp_path / "original"),
        require_diff=True,
    )

    cmd = _FakePopen.captured_cmd
    assert cmd is not None
    assert "--require-diff" in cmd


def test_require_diff_absent_when_not_set_in_background(tmp_path, monkeypatch):
    """--require-diff must NOT be forwarded when not set."""
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    state_dir = tmp_path / "state"
    state_dir.mkdir()

    worktree = tmp_path / "worktree"
    worktree.mkdir()
    (worktree / "TASK.md").write_text("body\n")

    monkeypatch.setattr(loop, "get_loop_state_dir", lambda: state_dir)
    _FakePopen.captured_cmd = None
    monkeypatch.setattr(executor.subprocess, "Popen", _FakePopen)

    executor.run_verification_loop_background(
        cli_info={"command": ["fake"], "env": {}, "stdin_mode": "dash", "display": "fake"},
        original_content="body",
        cwd=str(worktree),
        log_dir=log_dir,
        prompt_number="999",
        model="fake",
        max_iterations=3,
        completion_marker="VERIFICATION_COMPLETE",
        execution_timestamp="20260703-000000",
        worktree_path=str(worktree),
        branch_name="prompt/999-test",
        original_repo_root=str(tmp_path / "original"),
        require_diff=False,
    )

    cmd = _FakePopen.captured_cmd
    assert cmd is not None
    assert "--require-diff" not in cmd


# ---------------------------------------------------------------------------
# wrap_prompt_with_verification_protocol: require_diff protocol text
# ---------------------------------------------------------------------------

def test_wrap_prompt_includes_diff_warning_when_require_diff():
    out = executor.wrap_prompt_with_verification_protocol(
        content="do work",
        iteration=1,
        max_iterations=3,
        completion_marker="VERIFICATION_COMPLETE",
        require_diff=True,
    )
    assert "independently verified" in out.lower()
    assert "NEEDS_RETRY" in out


def test_wrap_prompt_omits_diff_warning_when_no_require_diff():
    out = executor.wrap_prompt_with_verification_protocol(
        content="do work",
        iteration=1,
        max_iterations=3,
        completion_marker="VERIFICATION_COMPLETE",
        require_diff=False,
    )
    assert "independently verified" not in out.lower()
