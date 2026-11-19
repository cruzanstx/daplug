"""Codex unattended-flag compatibility (codex-cli 0.167.0 removed --full-auto)."""

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import loop  # noqa: E402
import models  # noqa: E402
from sandbox import raise_on_execution_error  # noqa: E402

NEW_CMD = ["codex", "exec", "--approve-for-me", "-m", "gpt-5.6-terra", "-"]


@pytest.fixture(autouse=True)
def _clear_probe_cache():
    models.codex_supports_approve_for_me.cache_clear()
    yield
    models.codex_supports_approve_for_me.cache_clear()


def test_new_codex_keeps_modern_flags(monkeypatch):
    monkeypatch.setattr(models, "codex_supports_approve_for_me", lambda *_a, **_k: True)
    assert models.apply_codex_compat(list(NEW_CMD)) == NEW_CMD


def test_old_codex_falls_back_to_full_auto(monkeypatch):
    monkeypatch.setattr(models, "codex_supports_approve_for_me", lambda *_a, **_k: False)
    assert models.apply_codex_compat(list(NEW_CMD)) == [
        "codex", "exec", "--full-auto", "-m", "gpt-5.6-terra", "-",
    ]


def test_non_codex_commands_untouched_and_not_probed(monkeypatch):
    def boom(*_a, **_k):
        raise AssertionError("probe must not run for non-codex commands")

    monkeypatch.setattr(models, "codex_supports_approve_for_me", boom)
    claude = ["claude", "--print", "--approve-for-me"]
    assert models.apply_codex_compat(claude) == claude
    bypass = ["codex", "exec", "--dangerously-bypass-approvals-and-sandbox", "-"]
    assert models.apply_codex_compat(bypass) == bypass
    assert models.apply_codex_compat([]) == []


def _fake_run(stdout, returncode=0, calls=None):
    def run(cmd, **_kwargs):
        if calls is not None:
            calls.append(cmd)
        return subprocess.CompletedProcess(cmd, returncode, stdout=stdout, stderr="")
    return run


def test_probe_detects_new_flag_and_caches(monkeypatch):
    calls = []
    help_text = "Usage: codex exec [OPTIONS] [PROMPT]\n  --approve-for-me  route approvals\n"
    monkeypatch.setattr(models.subprocess, "run", _fake_run(help_text, calls=calls))
    assert models.codex_supports_approve_for_me() is True
    assert models.codex_supports_approve_for_me() is True
    assert calls == [["codex", "exec", "--help"]]


def test_probe_detects_old_codex(monkeypatch):
    help_text = "Usage: codex exec [OPTIONS] [PROMPT]\n  --full-auto  low-friction sandboxed\n"
    monkeypatch.setattr(models.subprocess, "run", _fake_run(help_text))
    assert models.codex_supports_approve_for_me() is False


def test_probe_failure_keeps_modern_flags(monkeypatch):
    def raise_oserror(*_a, **_k):
        raise FileNotFoundError("codex")

    monkeypatch.setattr(models.subprocess, "run", raise_oserror)
    assert models.codex_supports_approve_for_me() is True


def test_get_cli_info_does_not_probe(monkeypatch):
    def boom(*_a, **_k):
        raise AssertionError("command building must not probe codex")

    monkeypatch.setattr(models, "codex_supports_approve_for_me", boom)
    monkeypatch.setattr(models, "_resolve_router_command", lambda *_a, **_k: None)
    info = models.get_cli_info("codex-high", cli_override="codex")
    assert info["command"][:3] == ["codex", "exec", "--approve-for-me"]


def test_fatal_launch_error_detects_codex_unexpected_argument(tmp_path):
    log_file = tmp_path / "iter1.log"
    cli_info = {
        "command": [
            sys.executable,
            "-c",
            "import sys; sys.stderr.write(\"error: unexpected argument '--full-auto' found\\nUsage: codex exec\\n\"); sys.exit(2)",
        ],
        "env": {},
        "stdin_mode": "stdin",
        "display": "Codex",
    }
    res = loop.run_cli_foreground(cli_info, "hello", str(tmp_path), log_file)
    assert res["status"] == "error"
    assert res["exit_code"] == 2
    assert res["fatal_launch_error"] is True
    assert "unexpected argument" in res["error"]


def test_fatal_launch_error_detects_exit_127(tmp_path):
    log_file = tmp_path / "iter1.log"
    cli_info = {
        "command": [
            sys.executable,
            "-c",
            "import sys; sys.stderr.write('codex: command not found\\n'); sys.exit(127)",
        ],
        "env": {},
        "stdin_mode": "stdin",
        "display": "Codex",
    }
    res = loop.run_cli_foreground(cli_info, "hello", str(tmp_path), log_file)
    assert res["status"] == "error"
    assert res["exit_code"] == 127
    assert res["fatal_launch_error"] is True
    assert "command not found" in res["error"]


def test_non_fatal_nonzero_exit_remains_retryable(tmp_path):
    log_file = tmp_path / "iter1.log"
    cli_info = {
        "command": [
            sys.executable,
            "-c",
            "import sys; sys.stderr.write('temporary upstream 503\\n'); sys.exit(1)",
        ],
        "env": {},
        "stdin_mode": "stdin",
        "display": "Codex",
    }
    res = loop.run_cli_foreground(cli_info, "hello", str(tmp_path), log_file)
    assert res["status"] == "completed"
    assert res["exit_code"] == 1
    assert "fatal_launch_error" not in res


def test_loop_aborts_immediately_and_propagates_fatal_launch_error(tmp_path, monkeypatch):
    state_dir = tmp_path / "loop-state"
    state_dir.mkdir()
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    monkeypatch.setattr(loop, "get_loop_state_dir", lambda: state_dir)

    counter_file = tmp_path / "calls.txt"
    cli_info = {
        "command": [
            sys.executable,
            "-c",
            (
                "import pathlib, sys; "
                f"p = pathlib.Path({str(counter_file)!r}); "
                "p.write_text(p.read_text() + 'x' if p.exists() else 'x'); "
                "sys.stderr.write(\"error: unexpected argument '--full-auto' found\\n\"); "
                "sys.exit(2)"
            ),
        ],
        "env": {},
        "stdin_mode": "stdin",
        "display": "Codex",
    }

    result = loop.run_verification_loop(
        cli_info=cli_info,
        original_content="do the thing",
        cwd=str(tmp_path),
        log_dir=log_dir,
        prompt_number="299",
        model="codex",
        max_iterations=3,
        completion_marker="VERIFICATION_COMPLETE",
        execution_timestamp="20261119-104000",
    )

    # Must not retry invalid CLI arguments
    assert counter_file.read_text() == "x"
    assert result["status"] == "error"
    assert result["final_status"] == "failed"
    assert result["exit_code"] == 2
    assert result["fatal_launch_error"] is True
    assert "unexpected argument" in result["error"]

    # Outer executor propagates fatal launch errors as non-zero via raise_on_execution_error
    with pytest.raises(RuntimeError, match="unexpected argument"):
        raise_on_execution_error(result)


@pytest.mark.skipif(shutil.which("codex") is None, reason="codex binary not installed")
def test_codex_cli_parse_smoke_no_inference():
    proc = subprocess.run(
        ["codex", "exec", *models.CODEX_UNATTENDED_FLAGS, "--help"],
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert proc.returncode == 0, proc.stderr or proc.stdout
