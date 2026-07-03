"""Tests for worktree base-branch detection (#15) and isolation guard (#14)."""
import importlib.util
import json
import os
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

import loop  # noqa: E402
import paths  # noqa: E402


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


# -----------------------
# detect_default_branch
# -----------------------

def test_detect_default_branch_returns_current_when_no_origin_main(tmp_path):
    repo = _init_repo(tmp_path / "r", initial_branch="main")
    assert executor.detect_default_branch(repo) == "main"


def test_detect_default_branch_returns_current_when_no_origin_master(tmp_path):
    repo = _init_repo(tmp_path / "r", initial_branch="master")
    assert executor.detect_default_branch(repo) == "master"


def test_detect_default_branch_prefers_origin_head_over_current(tmp_path):
    """origin/HEAD should win over the locally checked-out branch."""
    upstream = _init_repo(tmp_path / "upstream", initial_branch="master")
    clone = tmp_path / "clone"
    _run(["git", "clone", str(upstream), str(clone)], cwd=tmp_path)
    # Check out a side branch locally so current != origin's HEAD
    _run(["git", "checkout", "-b", "side"], cwd=clone)
    assert executor.detect_default_branch(clone) == "master"


def test_detect_default_branch_falls_back_to_main_outside_repo(tmp_path):
    bare = tmp_path / "not-a-repo"
    bare.mkdir()
    assert executor.detect_default_branch(bare) == "main"


# -----------------------
# repo_state_snapshot
# -----------------------

def test_repo_state_snapshot_clean_repo_returns_empty(tmp_path):
    repo = _init_repo(tmp_path / "r")
    assert executor.repo_state_snapshot(str(repo)) == {"modified": {}, "untracked": set()}


def test_repo_state_snapshot_detects_untracked(tmp_path):
    repo = _init_repo(tmp_path / "r")
    (repo / "new.txt").write_text("x")
    snap = executor.repo_state_snapshot(str(repo))
    assert snap["modified"] == {}
    assert snap["untracked"] == {"new.txt"}


def test_repo_state_snapshot_detects_modified(tmp_path):
    repo = _init_repo(tmp_path / "r")
    (repo / "README.md").write_text("changed\n")
    snap = executor.repo_state_snapshot(str(repo))
    assert set(snap["modified"]) == {"README.md"}
    assert snap["modified"]["README.md"]
    assert snap["untracked"] == set()


def test_repo_state_snapshot_bad_path_returns_empty(tmp_path):
    assert executor.repo_state_snapshot(str(tmp_path / "does-not-exist")) == {
        "modified": {},
        "untracked": set(),
    }


def test_repo_state_snapshot_detects_change_between_snapshots(tmp_path):
    """Simulates the loop's before/after comparison."""
    repo = _init_repo(tmp_path / "r")
    before = executor.repo_state_snapshot(str(repo))
    (repo / "leaked.txt").write_text("subagent wrote here")
    after = executor.repo_state_snapshot(str(repo))
    assert before != after
    assert after["untracked"] == {"leaked.txt"}


def test_repo_state_snapshot_ignores_stat_only_mtime_change(tmp_path):
    repo = _init_repo(tmp_path / "r")
    before = executor.repo_state_snapshot(str(repo))
    os.utime(repo / "README.md", None)
    after = executor.repo_state_snapshot(str(repo))
    assert after == before


# ---------------------------------------------
# wrap_prompt_with_verification_protocol guard
# ---------------------------------------------

BLOCK_TAG = "<critical_isolation_boundary>"


def _wrap(**overrides):
    base = dict(
        content="do work",
        iteration=1,
        max_iterations=3,
        completion_marker="VERIFICATION_COMPLETE",
        worktree_path=None,
        branch_name=None,
        history=[],
        original_repo_root=None,
    )
    base.update(overrides)
    return executor.wrap_prompt_with_verification_protocol(**base)


def test_isolation_block_present_when_worktree_and_original_differ(tmp_path):
    wt = tmp_path / "worktrees" / "x"
    orig = tmp_path / "repo"
    out = _wrap(worktree_path=str(wt), original_repo_root=str(orig))
    assert BLOCK_TAG in out
    assert str(wt) in out
    assert str(orig) in out


def test_isolation_block_absent_when_no_original(tmp_path):
    out = _wrap(worktree_path=str(tmp_path / "wt"))
    assert BLOCK_TAG not in out


def test_isolation_block_absent_when_no_worktree(tmp_path):
    out = _wrap(original_repo_root=str(tmp_path / "r"))
    assert BLOCK_TAG not in out


def test_isolation_block_absent_when_paths_equal(tmp_path):
    same = str(tmp_path / "same")
    out = _wrap(worktree_path=same, original_repo_root=same)
    assert BLOCK_TAG not in out


def test_isolation_block_absent_when_paths_equal_after_resolution(tmp_path):
    """Block should not fire on symlink/trailing-slash variants of the same path."""
    target = tmp_path / "repo"
    target.mkdir()
    out = _wrap(worktree_path=str(target), original_repo_root=str(target) + "/")
    assert BLOCK_TAG not in out


def test_isolation_block_warns_about_subagent_prompts(tmp_path):
    out = _wrap(
        worktree_path=str(tmp_path / "wt"),
        original_repo_root=str(tmp_path / "main"),
    )
    assert "subagent" in out.lower() or "sub-prompt" in out.lower()


def test_isolation_block_mentions_warning_consequence(tmp_path):
    """The wrapper must describe warning-only original-checkout dirtiness handling."""
    out = _wrap(
        worktree_path=str(tmp_path / "wt"),
        original_repo_root=str(tmp_path / "main"),
    )
    assert "bwrap" in out
    assert "ORIGINAL_CHECKOUT_DIRTIED" in out
    assert "warning" in out.lower()


# -----------------------
# create_worktree default base-branch
# -----------------------

def test_create_worktree_auto_detects_master_when_base_branch_none(tmp_path, monkeypatch):
    """Regression for #15: must not hardcode 'main' when repo uses 'master'."""
    repo = _init_repo(tmp_path / "r", initial_branch="master")
    monkeypatch.setattr(paths, "_read_config_value", lambda *a, **kw: None)
    prompts_dir = repo / "prompts"
    prompts_dir.mkdir()
    prompt_file = prompts_dir / "001-test.md"
    prompt_file.write_text("body\n")

    info = executor.create_worktree(repo, prompt_file, base_branch=None)
    assert info.get("conflict") is not True, info
    assert info["base_branch"] == "master"
    # Sanity: worktree was actually created on disk
    assert Path(info["worktree_path"]).exists()


def test_create_worktree_honors_explicit_base_branch_override(tmp_path, monkeypatch):
    """--base-branch must still win over auto-detection."""
    repo = _init_repo(tmp_path / "r", initial_branch="main")
    # Create an alternate branch the user might want to base off
    _run(["git", "checkout", "-b", "develop"], cwd=repo)
    _run(["git", "checkout", "main"], cwd=repo)

    monkeypatch.setattr(paths, "_read_config_value", lambda *a, **kw: None)
    prompts_dir = repo / "prompts"
    prompts_dir.mkdir()
    prompt_file = prompts_dir / "001-test.md"
    prompt_file.write_text("body\n")

    info = executor.create_worktree(repo, prompt_file, base_branch="develop")
    assert info.get("conflict") is not True, info
    assert info["base_branch"] == "develop"


# --------------------------------------------------------------------
# End-to-end: run_verification_loop warns on original checkout dirtiness (#14/#20)
# --------------------------------------------------------------------

@pytest.fixture()
def loop_env(tmp_path, monkeypatch):
    """Common fixture: real git repo as the "original" + isolated state/log dirs."""
    original = _init_repo(tmp_path / "original", initial_branch="main")
    worktree = tmp_path / "worktree"
    worktree.mkdir()
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
        "original": original,
        "worktree": worktree,
        "log_dir": log_dir,
        "state_dir": state_dir,
        "cli_info": cli_info,
    }


def _make_fake_cli(*, write_marker: bool, side_effect_file: Path | None,
                   marker: str = "VERIFICATION_COMPLETE"):
    """Build a stand-in for run_cli_foreground.

    write_marker: emit a real completion marker in the log file
    side_effect_file: optional file path to create on disk (simulates a breach)
    """
    def fake_run(cli_info, content, cwd, log_file, sandbox_config=None):
        with open(log_file, "w") as f:
            # Replay the prompt body up to the instructions end so the marker
            # check searches the right region.
            f.write(content)
            f.write("\n--- model output ---\n")
            if write_marker:
                f.write(f"<verification>{marker}</verification>\n")
        if side_effect_file is not None:
            side_effect_file.parent.mkdir(parents=True, exist_ok=True)
            side_effect_file.write_text("leaked\n")
        return {"status": "ok", "exit_code": 0}
    return fake_run


def _call_loop(env, *, monkeypatch, fake_cli, original_repo_root,
               worktree_path, max_iterations=2):
    monkeypatch.setattr(loop, "run_cli_foreground", fake_cli)
    return executor.run_verification_loop(
        cli_info=env["cli_info"],
        original_content="do the thing",
        cwd=str(worktree_path) if worktree_path else str(env["original"]),
        log_dir=env["log_dir"],
        prompt_number="999",
        model="fake",
        max_iterations=max_iterations,
        completion_marker="VERIFICATION_COMPLETE",
        execution_timestamp="20260530-000000",
        worktree_path=str(worktree_path) if worktree_path else None,
        branch_name="prompt/999-test" if worktree_path else None,
        original_repo_root=str(original_repo_root) if original_repo_root else None,
    )


def test_loop_warns_but_continues_when_original_is_dirtied(loop_env, monkeypatch):
    """Original checkout dirtiness is logged but marker handling still completes."""
    leak = loop_env["original"] / "leaked-by-model.txt"
    fake_cli = _make_fake_cli(write_marker=True, side_effect_file=leak)

    result = _call_loop(
        loop_env,
        monkeypatch=monkeypatch,
        fake_cli=fake_cli,
        original_repo_root=loop_env["original"],
        worktree_path=loop_env["worktree"],
    )

    assert result["status"] == "completed"
    assert result["final_status"] == "completed"
    assert len(result["iterations"]) == 1
    assert result["iterations"][0]["marker_found"] is True
    assert result["original_checkout_warnings"]

    # State file records the warning and still persists normal completion.
    state_file = Path(result["state_file"])
    state = json.loads(state_file.read_text())
    assert state["status"] == "completed"
    assert state["iteration"] == 1
    warning = state["original_checkout_warnings"][0]
    assert warning["iteration"] == 1
    assert warning["modified"] == []
    assert warning["new_untracked"] == ["leaked-by-model.txt"]

    # Loop log surfaces the warning.
    loop_log_text = Path(result["loop_log"]).read_text()
    assert "ORIGINAL_CHECKOUT_DIRTIED" in loop_log_text
    assert "leaked-by-model.txt" in loop_log_text


def test_loop_completes_normally_when_original_untouched(loop_env, monkeypatch):
    """Sanity: a clean run still reaches the completion marker."""
    fake_cli = _make_fake_cli(write_marker=True, side_effect_file=None)

    result = _call_loop(
        loop_env,
        monkeypatch=monkeypatch,
        fake_cli=fake_cli,
        original_repo_root=loop_env["original"],
        worktree_path=loop_env["worktree"],
    )

    assert result["status"] == "completed"
    assert result["final_status"] == "completed"
    assert len(result["iterations"]) == 1
    assert result["iterations"][0]["marker_found"] is True


def test_loop_guard_inactive_without_worktree(loop_env, monkeypatch):
    """When run without --worktree, dirtying the cwd repo is expected: don't trip the guard."""
    leak = loop_env["original"] / "expected-edit.txt"
    fake_cli = _make_fake_cli(write_marker=True, side_effect_file=leak)

    result = _call_loop(
        loop_env,
        monkeypatch=monkeypatch,
        fake_cli=fake_cli,
        original_repo_root=loop_env["original"],
        worktree_path=None,  # No worktree => guard must not fire
    )

    assert result["status"] == "completed"
    assert result["final_status"] == "completed"


def test_loop_guard_inactive_when_worktree_path_equals_original(loop_env, monkeypatch):
    """Edge case: if worktree_path == original_repo_root (degenerate config),
    the guard would generate false positives. Verify it stays inactive."""
    leak = loop_env["original"] / "in-place-edit.txt"
    fake_cli = _make_fake_cli(write_marker=True, side_effect_file=leak)

    result = _call_loop(
        loop_env,
        monkeypatch=monkeypatch,
        fake_cli=fake_cli,
        original_repo_root=loop_env["original"],
        worktree_path=loop_env["original"],  # identical
    )

    assert result["status"] == "completed"


# --------------------------------------------------------------------
# Regression: background loop spawner must forward worktree context (#14)
# --------------------------------------------------------------------
#
# In 0.27.1 the wrapper warning and the `git status` snapshot guard were
# silently disabled on the default `/run-prompt --loop` path because
# `run_verification_loop_background` built the re-entry command without
# `--worktree-path`. Inside the foreground re-entry that meant
# `args.worktree=False` -> `worktree_path=None` -> `guard_active=False` and
# the `<critical_isolation_boundary>` block was never injected.
#
# The smoke run that proved this leaked files into the original checkout
# and the guard never tripped. These tests pin the forwarding so it
# can't silently regress again.


class _FakePopen:
    """Captures the spawned command and pretends to be a running process."""
    captured_cmd = None
    captured_cwd = None

    def __init__(self, cmd, cwd=None, **_kwargs):
        type(self).captured_cmd = list(cmd)
        type(self).captured_cwd = cwd
        self.pid = 4242


def _bg_kwargs(tmp_path, *, worktree_path, branch_name):
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    cli_info = {"command": ["fake"], "env": {}, "stdin_mode": "dash", "display": "fake"}
    return dict(
        cli_info=cli_info,
        original_content="body",
        cwd=str(worktree_path) if worktree_path else str(tmp_path),
        log_dir=log_dir,
        prompt_number="999",
        model="fake",
        max_iterations=1,
        completion_marker="VERIFICATION_COMPLETE",
        execution_timestamp="20260602-000000",
        worktree_path=str(worktree_path) if worktree_path else None,
        branch_name=branch_name,
        original_repo_root=str(tmp_path / "original"),
    )


def test_bg_spawner_forwards_worktree_path_and_branch(tmp_path, monkeypatch):
    """When a worktree is active, the re-entry cmd MUST carry --worktree-path
    and --branch-name so the foreground re-entry can re-activate the isolation
    guard and the <critical_isolation_boundary> wrapper."""
    worktree = tmp_path / "worktree"
    worktree.mkdir()
    (worktree / "TASK.md").write_text("body\n")

    _FakePopen.captured_cmd = None
    monkeypatch.setattr(executor.subprocess, "Popen", _FakePopen)
    monkeypatch.setattr(loop, "get_loop_state_dir", lambda: tmp_path / "state")
    (tmp_path / "state").mkdir()

    executor.run_verification_loop_background(
        **_bg_kwargs(tmp_path, worktree_path=worktree, branch_name="prompt/999-test"),
    )

    cmd = _FakePopen.captured_cmd
    assert cmd is not None, "Popen was not called"
    assert "--worktree-path" in cmd, f"missing --worktree-path in {cmd}"
    assert cmd[cmd.index("--worktree-path") + 1] == str(worktree)
    assert "--branch-name" in cmd, f"missing --branch-name in {cmd}"
    assert cmd[cmd.index("--branch-name") + 1] == "prompt/999-test"
    # The foreground re-entry marker must be present, otherwise the re-entry
    # would create yet another worktree.
    assert "--loop-foreground" in cmd


def test_bg_spawner_omits_worktree_flags_when_no_worktree(tmp_path, monkeypatch):
    """Without a worktree, --worktree-path / --branch-name must NOT be sent —
    the re-entry resolves the prompt by number from the current repo."""
    _FakePopen.captured_cmd = None
    monkeypatch.setattr(executor.subprocess, "Popen", _FakePopen)
    monkeypatch.setattr(loop, "get_loop_state_dir", lambda: tmp_path / "state")
    (tmp_path / "state").mkdir()

    executor.run_verification_loop_background(
        **_bg_kwargs(tmp_path, worktree_path=None, branch_name=None),
    )

    cmd = _FakePopen.captured_cmd
    assert cmd is not None
    assert "--worktree-path" not in cmd
    assert "--branch-name" not in cmd
    # The prompt number must be the positional arg instead.
    assert cmd[-1] == "999"


def test_parser_accepts_worktree_path_and_branch_name(monkeypatch):
    """The new flags must round-trip through argparse so the spawner's output
    is actually consumable by the re-entry process."""
    parser_argv = [
        "--loop", "--loop-foreground",
        "--model", "codex",
        "--cwd", "/tmp/wt",
        "--worktree-path", "/tmp/wt",
        "--branch-name", "prompt/999-x",
        "--original-repo-root", "/tmp/orig",
        "--prompt-file", "/tmp/wt/TASK.md",
        "--prompt-number", "999",
    ]
    import argparse as _ap
    monkeypatch.setattr(sys, "argv", ["executor.py"] + parser_argv)

    # Short-circuit main() right after parse_args so we don't run any work.
    called = {}
    real_parse = _ap.ArgumentParser.parse_args

    def _capture(self, *a, **kw):
        ns = real_parse(self, *a, **kw)
        called["ns"] = ns
        raise SystemExit(0)

    monkeypatch.setattr(_ap.ArgumentParser, "parse_args", _capture)
    with pytest.raises(SystemExit):
        executor.main()

    ns = called["ns"]
    assert ns.worktree_path == "/tmp/wt"
    assert ns.branch_name == "prompt/999-x"
