import json
import sys
from pathlib import Path

import pytest

SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.append(str(SCRIPT_DIR))

import executor  # noqa: E402


@pytest.fixture()
def no_router(monkeypatch):
    monkeypatch.setattr(executor, "_resolve_router_command", lambda *_args, **_kwargs: None)


@pytest.fixture()
def prompt_repo(tmp_path, monkeypatch):
    prompts_dir = tmp_path / "prompts"
    prompts_dir.mkdir()
    prompt_file = prompts_dir / "001-test-prompt.md"
    prompt_file.write_text("# Test Prompt\n\nDo the thing.\n")

    logs_dir = tmp_path / "logs"
    logs_dir.mkdir()

    monkeypatch.setattr(executor, "get_repo_root", lambda: tmp_path)
    monkeypatch.setattr(executor, "get_cli_logs_dir", lambda _repo_root: logs_dir)
    monkeypatch.setattr(executor, "_resolve_router_command", lambda *_args, **_kwargs: None)

    return tmp_path, logs_dir, prompt_file


@pytest.fixture()
def loop_state_dir(tmp_path, monkeypatch):
    state_dir = tmp_path / "loop-state"
    state_dir.mkdir()
    monkeypatch.setattr(executor, "get_loop_state_dir", lambda: state_dir)
    return state_dir


def _reasoning_value(command: list[str]) -> str:
    joined = " ".join(command)
    if 'model_reasoning_effort="high"' in joined:
        return "high"
    if 'model_reasoning_effort="xhigh"' in joined:
        return "xhigh"
    return ""


def test_variant_parsing_precedence_over_alias_defaults(no_router, tmp_path):
    info_default = executor.get_cli_info("codex-high", repo_root=tmp_path)
    assert _reasoning_value(info_default["command"]) == "high"

    info_override = executor.get_cli_info("codex-high", repo_root=tmp_path, variant="xhigh")
    assert _reasoning_value(info_override["command"]) == "xhigh"

    info_none = executor.get_cli_info("codex-high", repo_root=tmp_path, variant="none")
    assert _reasoning_value(info_none["command"]) == ""


def test_codex_variant_mapping_high_and_xhigh(no_router, tmp_path):
    high_info = executor.get_cli_info("codex", repo_root=tmp_path, variant="high")
    xhigh_info = executor.get_cli_info("codex", repo_root=tmp_path, variant="xhigh")

    assert _reasoning_value(high_info["command"]) == "high"
    assert _reasoning_value(xhigh_info["command"]) == "xhigh"


def test_opencode_command_includes_variant_when_requested(no_router, tmp_path):
    info = executor.get_cli_info("codex", repo_root=tmp_path, cli_override="opencode", variant="high")

    assert info["selected_cli"] == "opencode"
    assert info["command"][:4] == ["opencode", "run", "--format", "json"]
    assert "--variant" in info["command"]
    assert info["command"][info["command"].index("--variant") + 1] == "high"


def test_explicit_cli_opencode_respected_for_supported_model(no_router, tmp_path):
    info = executor.get_cli_info("gpt52-high", repo_root=tmp_path, cli_override="opencode")

    assert info["selected_cli"] == "opencode"
    assert info["command"][0] == "opencode"


def test_explicit_cli_opencode_errors_for_unsupported_model(no_router, tmp_path):
    with pytest.raises(ValueError, match="--cli opencode is not supported with --model gemini"):
        executor.get_cli_info("gemini", repo_root=tmp_path, cli_override="opencode")


def test_explicit_cli_override_takes_precedence_over_router_default(tmp_path, monkeypatch):
    monkeypatch.setattr(
        executor,
        "_resolve_router_command",
        lambda *_args, **_kwargs: ("codex", "openai:gpt-5.3-codex", ["codex", "exec", "--full-auto"]),
    )

    info = executor.get_cli_info("codex", repo_root=tmp_path, cli_override="opencode", variant="high")
    assert info["selected_cli"] == "opencode"
    assert info["model_id"] == "openai:gpt-5.3-codex"
    assert info["command"][:4] == ["opencode", "run", "--format", "json"]
    assert "--variant" in info["command"]
    assert info["command"][info["command"].index("--variant") + 1] == "high"
    assert "via OpenCode" in info["display"]


def test_default_router_selection_unchanged_without_cli_override(tmp_path, monkeypatch):
    monkeypatch.setattr(
        executor,
        "_resolve_router_command",
        lambda *_args, **_kwargs: ("opencode", "openai:gpt-5.3-codex", ["opencode", "run", "--format", "json"]),
    )

    info = executor.get_cli_info("codex", repo_root=tmp_path)
    assert info["selected_cli"] == "opencode"
    assert info["command"][:4] == ["opencode", "run", "--format", "json"]


def test_legacy_aliases_remain_backward_compatible(no_router, tmp_path):
    codex_alias = executor.get_cli_info("codex-xhigh", repo_root=tmp_path)
    gpt_alias = executor.get_cli_info("gpt52-high", repo_root=tmp_path)

    assert codex_alias["command"][0:3] == ["codex", "exec", "--full-auto"]
    assert _reasoning_value(codex_alias["command"]) == "xhigh"

    assert gpt_alias["command"][0:5] == ["codex", "exec", "--full-auto", "-m", "gpt-5.2"]
    assert _reasoning_value(gpt_alias["command"]) == "high"


def test_invalid_variant_combinations_error_actionably(no_router, tmp_path, monkeypatch):
    with pytest.raises(ValueError, match="Codex supports high/xhigh only"):
        executor.get_cli_info("codex", repo_root=tmp_path, variant="medium")

    monkeypatch.setattr(executor.shutil, "which", lambda name: "/usr/bin/claude" if name == "claude" else None)
    with pytest.raises(ValueError, match="is not supported with --model cc-sonnet"):
        executor.get_cli_info("cc-sonnet", repo_root=tmp_path, variant="high")


def test_main_info_only_honors_explicit_variant_precedence(prompt_repo, monkeypatch, capsys):
    argv = [
        "executor.py",
        "001",
        "--model",
        "codex-high",
        "--variant",
        "none",
    ]
    monkeypatch.setattr(sys, "argv", argv)

    executor.main()
    parsed = json.loads(capsys.readouterr().out)

    assert parsed["model"] == "codex-high"
    assert parsed["selected_cli"] == "codex"
    assert parsed["variant"] is None
    assert _reasoning_value(parsed["cli_command"]) == ""


def test_main_run_smoke_renders_codex_variant_command(prompt_repo, monkeypatch, capsys):
    _repo_root, _logs_dir, _prompt_file = prompt_repo
    captured = {}

    def fake_run_cli(cli_info, content, cwd, log_file):
        captured["command"] = list(cli_info["command"])
        Path(log_file).write_text("ok\n")
        return {"status": "completed", "exit_code": 0, "log": str(log_file)}

    monkeypatch.setattr(executor, "run_cli", fake_run_cli)
    argv = [
        "executor.py",
        "001",
        "--model",
        "codex",
        "--variant",
        "high",
        "--run",
    ]
    monkeypatch.setattr(sys, "argv", argv)

    executor.main()
    parsed = json.loads(capsys.readouterr().out)

    assert parsed["selected_cli"] == "codex"
    assert _reasoning_value(captured["command"]) == "high"
    assert parsed["prompts"][0]["execution"]["status"] == "completed"


def test_main_run_smoke_renders_opencode_variant_command(prompt_repo, monkeypatch, capsys):
    _repo_root, _logs_dir, _prompt_file = prompt_repo
    captured = {}

    def fake_run_cli(cli_info, content, cwd, log_file):
        captured["command"] = list(cli_info["command"])
        Path(log_file).write_text("ok\n")
        return {"status": "completed", "exit_code": 0, "log": str(log_file)}

    monkeypatch.setattr(executor, "run_cli", fake_run_cli)
    argv = [
        "executor.py",
        "001",
        "--model",
        "codex",
        "--cli",
        "opencode",
        "--variant",
        "medium",
        "--run",
    ]
    monkeypatch.setattr(sys, "argv", argv)

    executor.main()
    parsed = json.loads(capsys.readouterr().out)

    assert parsed["selected_cli"] == "opencode"
    assert captured["command"][0:4] == ["opencode", "run", "--format", "json"]
    assert "--variant" in captured["command"]
    assert captured["command"][captured["command"].index("--variant") + 1] == "medium"
    assert parsed["prompts"][0]["execution"]["status"] == "completed"


def test_loop_background_propagates_cli_and_variant_flags(tmp_path, loop_state_dir, monkeypatch):
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

    executor.run_verification_loop_background(
        cli_info={"command": ["codex"], "env": {}, "stdin_mode": "dash"},
        original_content="# Test\n\nDo the thing.\n",
        cwd=str(tmp_path),
        log_dir=log_dir,
        prompt_number="001",
        model="codex",
        max_iterations=3,
        completion_marker="VERIFICATION_COMPLETE",
        execution_timestamp="20260119-150550",
        worktree_path=None,
        branch_name=None,
        cli_override="opencode",
        variant="none",
    )

    cmd = captured["cmd"]
    assert "--cli" in cmd
    assert cmd[cmd.index("--cli") + 1] == "opencode"
    assert "--variant" in cmd
    assert cmd[cmd.index("--variant") + 1] == "none"
