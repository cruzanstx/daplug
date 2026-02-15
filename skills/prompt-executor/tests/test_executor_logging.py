import json
import sys
from pathlib import Path

import pytest

SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.append(str(SCRIPT_DIR))

import executor  # noqa: E402


@pytest.fixture()
def loop_state_dir(tmp_path, monkeypatch):
    state_dir = tmp_path / "loop-state"
    state_dir.mkdir()
    monkeypatch.setattr(executor, "get_loop_state_dir", lambda: state_dir)
    return state_dir


def test_run_verification_loop_creates_loop_log_and_uses_timestamp(tmp_path, loop_state_dir, monkeypatch):
    log_dir = tmp_path / "logs"
    log_dir.mkdir()

    completion_marker = "VERIFICATION_COMPLETE"
    execution_timestamp = "20260119-150550"

    def fake_run_cli_foreground(cli_info, content, cwd, log_file):
        Path(log_file).write_text(
            f"{executor.INSTRUCTIONS_END_SENTINEL}\n"
            f"<verification>{completion_marker}</verification>\n"
        )
        return {"status": "completed", "exit_code": 0, "log": str(log_file)}

    monkeypatch.setattr(executor, "run_cli_foreground", fake_run_cli_foreground)

    result = executor.run_verification_loop(
        cli_info={"command": ["codex"], "env": {}, "stdin_mode": "dash"},
        original_content="# Test\n\nDo the thing.\n",
        cwd=str(tmp_path),
        log_dir=log_dir,
        prompt_number="001",
        model="codex",
        max_iterations=3,
        completion_marker=completion_marker,
        execution_timestamp=execution_timestamp,
        worktree_path=None,
        branch_name=None,
    )

    assert result["status"] == "completed"
    assert result["loop_log"].endswith(f"codex-001-loop-{execution_timestamp}.log")
    assert Path(result["loop_log"]).exists()

    assert result["iterations"][0]["iteration"] == 1
    assert result["iterations"][0]["log_file"].endswith(f"codex-001-iter1-{execution_timestamp}.log")
    assert Path(result["iterations"][0]["log_file"]).exists()

    loop_log_content = Path(result["loop_log"]).read_text()
    assert "Loop Execution Log" in loop_log_content
    assert "Starting iteration 1/3" in loop_log_content


def test_run_verification_loop_background_passes_execution_timestamp(tmp_path, loop_state_dir, monkeypatch):
    log_dir = tmp_path / "logs"
    log_dir.mkdir()

    captured = {}

    class DummyProc:
        pid = 4242

    def fake_popen(cmd, **kwargs):
        captured["cmd"] = cmd
        stdout_handle = kwargs.get("stdout")
        if stdout_handle:
            stdout_handle.write("fake popen output\n")
            stdout_handle.close()
        return DummyProc()

    monkeypatch.setattr(executor.subprocess, "Popen", fake_popen)

    execution_timestamp = "20260119-150550"
    result = executor.run_verification_loop_background(
        cli_info={"command": ["codex"], "env": {}, "stdin_mode": "dash"},
        original_content="# Test\n\nDo the thing.\n",
        cwd=str(tmp_path),
        log_dir=log_dir,
        prompt_number="001",
        model="codex",
        max_iterations=3,
        completion_marker="VERIFICATION_COMPLETE",
        execution_timestamp=execution_timestamp,
        worktree_path=None,
        branch_name=None,
    )

    assert result["status"] == "loop_running"
    assert result["loop_log"].endswith(f"codex-001-loop-{execution_timestamp}.log")
    assert Path(result["loop_log"]).exists()

    cmd = captured["cmd"]
    assert "--execution-timestamp" in cmd
    assert cmd[cmd.index("--execution-timestamp") + 1] == execution_timestamp

    loop_log_content = Path(result["loop_log"]).read_text()
    assert f"# Started: {execution_timestamp}" in loop_log_content

    # State file is written under the patched loop state dir
    state_file = loop_state_dir / "001.json"
    assert state_file.exists()
    state = json.loads(state_file.read_text())
    assert state["execution_timestamp"] == execution_timestamp


def test_main_loop_foreground_sets_prompt_log_to_loop_log(tmp_path, loop_state_dir, monkeypatch, capsys):
    logs_dir = tmp_path / "logs"
    logs_dir.mkdir()

    task_file = tmp_path / "TASK.md"
    task_file.write_text("# Test Prompt\n\nDo the thing.\n")

    monkeypatch.setattr(executor, "get_repo_root", lambda: tmp_path)
    monkeypatch.setattr(executor, "get_cli_logs_dir", lambda _repo_root: logs_dir)

    completion_marker = "VERIFICATION_COMPLETE"
    execution_timestamp = "20260119-150550"

    def fake_run_cli_foreground(cli_info, content, cwd, log_file):
        Path(log_file).write_text(
            f"{executor.INSTRUCTIONS_END_SENTINEL}\n"
            f"<verification>{completion_marker}</verification>\n"
        )
        return {"status": "completed", "exit_code": 0, "log": str(log_file)}

    monkeypatch.setattr(executor, "run_cli_foreground", fake_run_cli_foreground)

    argv = [
        "executor.py",
        "--model",
        "codex",
        "--run",
        "--loop",
        "--loop-foreground",
        "--prompt-file",
        str(task_file),
        "--prompt-number",
        "001",
        "--execution-timestamp",
        execution_timestamp,
    ]
    monkeypatch.setattr(sys, "argv", argv)

    executor.main()
    out = capsys.readouterr().out
    parsed = json.loads(out)

    assert parsed["prompts"][0]["log"].endswith(f"codex-001-loop-{execution_timestamp}.log")
    assert parsed["prompts"][0]["execution"]["loop_log"].endswith(f"codex-001-loop-{execution_timestamp}.log")
    assert parsed["prompts"][0]["execution"]["iterations"][0]["log_file"].endswith(
        f"codex-001-iter1-{execution_timestamp}.log"
    )

    assert (logs_dir / f"codex-001-loop-{execution_timestamp}.log").exists()
    assert (logs_dir / f"codex-001-iter1-{execution_timestamp}.log").exists()


def test_standard_run_creates_log_at_displayed_path(tmp_path, monkeypatch, capsys):
    """Non-loop execution: displayed log path should match actual file created."""
    logs_dir = tmp_path / "logs"
    logs_dir.mkdir()

    prompts_dir = tmp_path / "prompts"
    prompts_dir.mkdir()
    prompt_file = prompts_dir / "001-test-prompt.md"
    prompt_file.write_text("# Test Prompt\n\nDo the thing.\n")

    monkeypatch.setattr(executor, "get_repo_root", lambda: tmp_path)
    monkeypatch.setattr(executor, "get_cli_logs_dir", lambda _repo_root: logs_dir)

    def fake_run_cli(cli_info, content, cwd, log_file):
        # Simulate CLI writing to log file
        Path(log_file).write_text("CLI output here\n")
        return {"status": "completed", "exit_code": 0, "log": str(log_file)}

    monkeypatch.setattr(executor, "run_cli", fake_run_cli)

    argv = [
        "executor.py",
        "--model",
        "codex",
        "--run",
        "001",
    ]
    monkeypatch.setattr(sys, "argv", argv)

    executor.main()
    out = capsys.readouterr().out
    parsed = json.loads(out)

    displayed_log = parsed["prompts"][0]["log"]
    assert Path(displayed_log).exists(), f"Displayed log path {displayed_log} does not exist"
    assert Path(displayed_log).read_text() == "CLI output here\n"


def test_claude_subagent_creates_log_in_cli_logs_dir(tmp_path, monkeypatch, capsys):
    """Claude subagent mode: log should be created in ~/.claude/cli-logs/, not /tmp/."""
    logs_dir = tmp_path / "cli-logs"
    logs_dir.mkdir()

    prompts_dir = tmp_path / "prompts"
    prompts_dir.mkdir()
    prompt_file = prompts_dir / "001-test-prompt.md"
    prompt_file.write_text("# Test Prompt\n\nDo the thing.\n")

    monkeypatch.setattr(executor, "get_repo_root", lambda: tmp_path)
    monkeypatch.setattr(executor, "get_cli_logs_dir", lambda _repo_root: logs_dir)

    argv = [
        "executor.py",
        "--model",
        "claude",  # Claude model has no CLI command
        "--run",
        "001",
    ]
    monkeypatch.setattr(sys, "argv", argv)

    executor.main()
    out = capsys.readouterr().out
    parsed = json.loads(out)

    displayed_log = parsed["prompts"][0]["log"]
    # Should be in cli-logs dir, not /tmp/
    assert str(logs_dir) in displayed_log, f"Log should be in {logs_dir}, got {displayed_log}"
    assert Path(displayed_log).exists(), f"Log file {displayed_log} should exist"

    # Log should contain metadata
    log_content = Path(displayed_log).read_text()
    assert "Claude Subagent Execution" in log_content
    assert "Prompt: 001-test-prompt.md" in log_content


def test_loop_resume_preserves_timestamp(tmp_path, loop_state_dir, monkeypatch):
    """Loop resume: timestamp should be preserved from original execution."""
    log_dir = tmp_path / "logs"
    log_dir.mkdir()

    original_timestamp = "20260119-100000"
    completion_marker = "VERIFICATION_COMPLETE"

    # Create existing state simulating interrupted loop at iteration 1
    existing_state = {
        "prompt_number": "001",
        "prompt_file": "",
        "model": "codex",
        "execution_timestamp": original_timestamp,
        "worktree_path": None,
        "branch_name": None,
        "execution_cwd": str(tmp_path),
        "iteration": 1,
        "max_iterations": 3,
        "completion_marker": completion_marker,
        "started_at": "2026-01-19T10:00:00",
        "last_updated_at": "2026-01-19T10:00:00",
        "status": "running",
        "history": [],
        "suggested_next_steps": [],
    }
    state_file = loop_state_dir / "001.json"
    state_file.write_text(json.dumps(existing_state))

    iteration_count = [0]

    def fake_run_cli_foreground(cli_info, content, cwd, log_file):
        iteration_count[0] += 1
        Path(log_file).write_text(
            f"{executor.INSTRUCTIONS_END_SENTINEL}\n"
            f"<verification>{completion_marker}</verification>\n"
        )
        return {"status": "completed", "exit_code": 0, "log": str(log_file)}

    monkeypatch.setattr(executor, "run_cli_foreground", fake_run_cli_foreground)

    # Resume with a DIFFERENT current timestamp - should use original
    new_timestamp = "20260119-120000"
    result = executor.run_verification_loop(
        cli_info={"command": ["codex"], "env": {}, "stdin_mode": "dash"},
        original_content="# Test\n\nDo the thing.\n",
        cwd=str(tmp_path),
        log_dir=log_dir,
        prompt_number="001",
        model="codex",
        max_iterations=3,
        completion_marker=completion_marker,
        execution_timestamp=new_timestamp,  # Different from original
        worktree_path=None,
        branch_name=None,
    )

    # Should use ORIGINAL timestamp, not new one
    assert result["loop_log"].endswith(f"codex-001-loop-{original_timestamp}.log")
    assert result["iterations"][0]["log_file"].endswith(f"codex-001-iter1-{original_timestamp}.log")

    # Verify state preserved original timestamp
    final_state = json.loads(state_file.read_text())
    assert final_state["execution_timestamp"] == original_timestamp


def test_loop_resume_updates_execution_cwd(tmp_path, loop_state_dir, monkeypatch):
    """Loop resume: execution_cwd should be refreshed to match the current invocation."""
    log_dir = tmp_path / "logs"
    log_dir.mkdir()

    original_timestamp = "20260119-100000"
    completion_marker = "VERIFICATION_COMPLETE"

    old_cwd = tmp_path / "old-worktree"
    old_cwd.mkdir()
    new_cwd = tmp_path / "new-worktree"
    new_cwd.mkdir()

    existing_state = {
        "prompt_number": "001",
        "prompt_file": "",
        "model": "codex",
        "execution_timestamp": original_timestamp,
        "worktree_path": str(old_cwd),
        "branch_name": "prompt/001-test",
        "execution_cwd": str(old_cwd),
        "iteration": 1,
        "max_iterations": 3,
        "completion_marker": completion_marker,
        "started_at": "2026-01-19T10:00:00",
        "last_updated_at": "2026-01-19T10:00:00",
        "status": "running",
        "history": [],
        "suggested_next_steps": [],
    }
    state_file = loop_state_dir / "001.json"
    state_file.write_text(json.dumps(existing_state))

    def fake_run_cli_foreground(cli_info, content, cwd, log_file):
        assert cwd == str(new_cwd)
        Path(log_file).write_text(
            f"{executor.INSTRUCTIONS_END_SENTINEL}\n"
            f"<verification>{completion_marker}</verification>\n"
        )
        return {"status": "completed", "exit_code": 0, "log": str(log_file)}

    monkeypatch.setattr(executor, "run_cli_foreground", fake_run_cli_foreground)

    result = executor.run_verification_loop(
        cli_info={"command": ["codex"], "env": {}, "stdin_mode": "dash"},
        original_content="# Test\n\nDo the thing.\n",
        cwd=str(new_cwd),
        log_dir=log_dir,
        prompt_number="001",
        model="codex",
        max_iterations=3,
        completion_marker=completion_marker,
        execution_timestamp="20260119-120000",
        worktree_path=str(new_cwd),
        branch_name="prompt/001-test",
    )

    assert result["status"] == "completed"

    updated_state = json.loads(state_file.read_text())
    assert updated_state["execution_timestamp"] == original_timestamp
    assert updated_state["execution_cwd"] == str(new_cwd)
    assert updated_state["worktree_path"] == str(new_cwd)


def test_run_verification_loop_fails_cleanly_when_execution_cwd_missing(tmp_path, loop_state_dir, monkeypatch):
    log_dir = tmp_path / "logs"
    log_dir.mkdir()

    missing_cwd = tmp_path / "missing-worktree"

    def fake_run_cli_foreground(*_args, **_kwargs):
        raise AssertionError("run_cli_foreground should not be called when execution_cwd is missing")

    monkeypatch.setattr(executor, "run_cli_foreground", fake_run_cli_foreground)

    result = executor.run_verification_loop(
        cli_info={"command": ["codex"], "env": {}, "stdin_mode": "dash"},
        original_content="# Test\n\nDo the thing.\n",
        cwd=str(missing_cwd),
        log_dir=log_dir,
        prompt_number="001",
        model="codex",
        max_iterations=3,
        completion_marker="VERIFICATION_COMPLETE",
        execution_timestamp="20260119-150550",
        worktree_path=str(missing_cwd),
        branch_name="prompt/001-test",
    )

    assert result["status"] == "error"
    assert "does not exist" in result["error"]
    assert Path(result["loop_log"]).exists()

    state = json.loads((loop_state_dir / "001.json").read_text())
    assert state["status"] == "failed"
    assert state["execution_cwd"] == str(missing_cwd)
    assert "does not exist" in state.get("failure_reason", "")


def test_get_cli_info_uses_router_for_cc_models(monkeypatch):
    """Executor should use cli-detector router when available for cc-* models."""
    repo_root = Path(__file__).resolve().parents[3]

    # Ensure claude CLI presence check doesn't depend on the host environment.
    monkeypatch.setattr(executor.shutil, "which", lambda name: "/usr/bin/claude" if name == "claude" else None)

    router_dir = repo_root / "skills" / "cli-detector" / "scripts"
    assert router_dir.exists()
    if str(router_dir) not in sys.path:
        sys.path.append(str(router_dir))
    import router as imported_router  # noqa: E402

    expected_cmd = ["claude", "--print", "--input-format", "text"]
    monkeypatch.setattr(imported_router, "resolve_model", lambda *_a, **_k: ("claude", "anthropic:sonnet", expected_cmd))

    info = executor.get_cli_info("cc-sonnet", repo_root=repo_root)
    assert info["command"] == expected_cmd
    assert info["stdin_mode"] == "stdin"


def test_run_cli_stdin_mode_does_not_put_prompt_in_argv(tmp_path, monkeypatch):
    """Large prompts should be passed via stdin for claude CLI runs (avoid argv-length limits)."""
    logs_dir = tmp_path / "logs"
    logs_dir.mkdir()
    log_file = logs_dir / "claude.log"

    monkeypatch.setattr(executor.shutil, "which", lambda name: "/usr/bin/claude" if name == "claude" else None)

    cli_info = executor.get_cli_info("cc-sonnet", repo_root=tmp_path)
    assert cli_info["stdin_mode"] == "stdin"

    captured = {}

    class _DummyStdin:
        def __init__(self):
            self.data = ""
            self.closed = False

        def write(self, text: str) -> None:
            self.data += text

        def close(self) -> None:
            self.closed = True

    class _DummyProc:
        pid = 12345

        def __init__(self):
            self.stdin = _DummyStdin()

    def fake_popen(cmd, **kwargs):
        captured["cmd"] = list(cmd)
        proc = _DummyProc()
        captured["stdin"] = proc.stdin
        return proc

    monkeypatch.setattr(executor.subprocess, "Popen", fake_popen)

    large_prompt = "x" * 250_000
    result = executor.run_cli(cli_info, large_prompt, cwd=str(tmp_path), log_file=log_file)

    assert result["status"] == "running"
    assert captured["cmd"] == cli_info["command"]  # prompt should not be appended to argv
    assert captured["stdin"].data == large_prompt
    assert captured["stdin"].closed is True
