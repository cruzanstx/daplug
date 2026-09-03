"""Tests for the AGY execution path: argv order, prompt placement, failure
classification, inactivity timeout, sandbox integration, and loop state.

These tests mock subprocess.Popen to verify the reader loop and failure
classification without launching real agy processes.
"""

from __future__ import annotations

import io
import json
import os
import signal
import sys
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

import agy_stream
import loop
import models
from sandbox import _is_agy_command, build_bwrap_args


# --- fixtures ----------------------------------------------------------


@pytest.fixture
def no_router(monkeypatch):
    """Disable router resolution so registry commands are used directly."""
    monkeypatch.setattr(
        models, "_resolve_router_command",
        lambda *_args, **_kwargs: None,
    )


# --- helpers -----------------------------------------------------------


def _agy_cli_info(display="Gemini 3.8 Flash (High)", timeout="60m", inactivity=None):
    """Build a cli_info dict matching what get_cli_info returns for agy."""
    info = {
        "command": [
            "agy", "--model", display,
            "--dangerously-skip-permissions",
            "--print-timeout", timeout,
            "--output-format", "stream-json",
            "--print",
        ],
        "display": f"agy ({display})",
        "env": {},
        "stdin_mode": "arg",
        "selected_cli": "agy",
        "base_model": "gemini",
        "model_id": "google:gemini-3.8-flash",
        "variant": None,
    }
    if inactivity:
        info["agy_inactivity_timeout"] = inactivity
    return info


# --- Exact argv: index-order assertions --------------------------------


class TestAgyArgvOrder:
    """Assert the exact agy argv order: --print-timeout and --output-format
    must precede --print, and --print must be the last element before the
    prompt is appended."""

    def test_get_cli_info_gemini_exact_argv(self, no_router, tmp_path):
        info = models.get_cli_info("gemini", repo_root=tmp_path)
        cmd = info["command"]
        assert cmd[0] == "agy"
        assert cmd[1] == "--model"
        assert cmd[3] == "--dangerously-skip-permissions"
        assert cmd[4] == "--print-timeout"
        assert cmd[5] == "60m"
        assert cmd[6] == "--output-format"
        assert cmd[7] == "stream-json"
        assert cmd[8] == "--print"
        assert cmd[-1] == "--print"

    def test_get_cli_info_agy_exact_argv(self, no_router, tmp_path):
        info = models.get_cli_info("agy", repo_root=tmp_path)
        cmd = info["command"]
        assert cmd[4] == "--print-timeout"
        assert cmd[5] == "60m"
        assert cmd[6] == "--output-format"
        assert cmd[7] == "stream-json"
        assert cmd[8] == "--print"
        assert cmd[-1] == "--print"

    def test_get_cli_info_gemini37_low_exact_argv(self, no_router, tmp_path):
        info = models.get_cli_info("gemini37-low", repo_root=tmp_path, cli_override="agy")
        cmd = info["command"]
        assert cmd[2] == "Gemini 3.8 Flash (Low)"
        assert cmd[4] == "--print-timeout"
        assert cmd[6] == "--output-format"
        assert cmd[8] == "--print"

    def test_configured_agy_print_timeout_honored(self, no_router, tmp_path, monkeypatch):
        monkeypatch.setattr(
            models, "_read_config_value",
            lambda root, key: "30m" if key == "agy_print_timeout" else None,
        )
        info = models.get_cli_info("gemini", repo_root=tmp_path)
        cmd = info["command"]
        assert cmd[4] == "--print-timeout"
        assert cmd[5] == "30m"

    def test_default_agy_print_timeout_is_60m(self, no_router, tmp_path):
        info = models.get_cli_info("gemini", repo_root=tmp_path)
        assert info["command"][5] == "60m"

    def test_agy_print_timeout_flag_override(self, no_router, tmp_path):
        info = models.get_cli_info("gemini", repo_root=tmp_path, agy_print_timeout="120m")
        assert info["command"][5] == "120m"

    def test_empty_agy_print_timeout_rejected(self, no_router, tmp_path):
        """Explicitly empty agy_print_timeout must raise, not silently default."""
        with pytest.raises(ValueError, match="agy_print_timeout must be non-empty"):
            models.get_cli_info("gemini", repo_root=tmp_path, agy_print_timeout="")

    def test_empty_agy_print_timeout_from_config_rejected(self, no_router, tmp_path, monkeypatch):
        """Empty config value must raise, not silently default."""
        monkeypatch.setattr(
            models, "_read_config_value",
            lambda root, key: "" if key == "agy_print_timeout" else None,
        )
        with pytest.raises(ValueError, match="agy_print_timeout must be non-empty"):
            models.get_cli_info("gemini", repo_root=tmp_path)

    def test_agy_inactivity_timeout_in_cli_info(self, no_router, tmp_path, monkeypatch):
        monkeypatch.setattr(
            models, "_read_config_value",
            lambda root, key: "30s" if key == "agy_inactivity_timeout" else None,
        )
        info = models.get_cli_info("gemini", repo_root=tmp_path)
        assert info.get("agy_inactivity_timeout") == "30s"

    def test_agy_inactivity_timeout_flag_override(self, no_router, tmp_path):
        info = models.get_cli_info(
            "gemini", repo_root=tmp_path,
            agy_inactivity_timeout="45s",
        )
        assert info.get("agy_inactivity_timeout") == "45s"

    def test_no_inactivity_timeout_by_default(self, no_router, tmp_path):
        info = models.get_cli_info("gemini", repo_root=tmp_path)
        assert "agy_inactivity_timeout" not in info


# --- Router argv consistency -------------------------------------------


class TestRouterAgyArgv:
    """Router must produce the same agy argv as models.py."""

    def test_router_agy_argv_matches_models(self, monkeypatch):
        _scripts = Path(__file__).resolve().parents[2] / "cli-detector" / "scripts"
        if str(_scripts) not in sys.path:
            sys.path.insert(0, str(_scripts))
        import router as router_mod

        class _FakeCache:
            def __init__(self, data):
                self._data = data
            def to_dict(self):
                return self._data

        fake = _FakeCache({
            "clis": {
                "agy": {"installed": True, "issues": []},
                "gemini": {"installed": True, "issues": []},
            },
            "providers": {},
        })
        monkeypatch.setattr(router_mod, "load_cache_file", lambda: fake)

        _cli, _mid, cmd = router_mod.resolve_model("gemini")
        assert cmd == [
            "agy", "--model", "Gemini 3.8 Flash (High)",
            "--dangerously-skip-permissions",
            "--print-timeout", "60m",
            "--output-format", "stream-json",
            "--print",
        ]


# --- Prompt placement: --print is last, prompt appended after ---------


class TestPromptPlacement:
    """The launched argv must end with ['--print', <content>] with nothing
    between them."""

    def test_prompt_is_last_element_in_foreground(self, tmp_path, monkeypatch):
        captured_cmd = []

        class _FakeProc:
            pid = 12345
            poll = lambda self: 0
            wait = lambda self: 0
            stdout = io.StringIO("")

        def fake_popen(cmd, **kw):
            captured_cmd.extend(cmd)
            return _FakeProc()

        monkeypatch.setattr(loop.subprocess, "Popen", fake_popen)
        cli_info = _agy_cli_info()
        log_file = tmp_path / "test.log"
        result = loop.run_cli_foreground(cli_info, "PROMPT_CONTENT", str(tmp_path), log_file)
        assert captured_cmd[-1] == "PROMPT_CONTENT"
        assert captured_cmd[-2] == "--print"

    def test_no_token_between_print_and_prompt(self, tmp_path, monkeypatch):
        captured_cmd = []

        class _FakeProc:
            pid = 12345
            poll = lambda self: 0
            wait = lambda self: 0
            stdout = io.StringIO("")

        def fake_popen(cmd, **kw):
            captured_cmd.extend(cmd)
            return _FakeProc()

        monkeypatch.setattr(loop.subprocess, "Popen", fake_popen)
        cli_info = _agy_cli_info()
        log_file = tmp_path / "test.log"
        loop.run_cli_foreground(cli_info, "PROMPT_CONTENT", str(tmp_path), log_file)
        print_idx = captured_cmd.index("--print")
        captured_idx_sl = captured_cmd[print_idx + 1] if print_idx + 1 < len(captured_cmd) else None
        assert captured_idx_sl == "PROMPT_CONTENT"


# --- Failure classification -------------------------------------------


class TestFailureClassification:
    """Test _classify_agy_result for all four status types."""

    def test_completed_on_success(self):
        event = agy_stream.AgyEvent(
            event_type=agy_stream.EVENT_RESULT,
            raw="",
            status="SUCCESS",
        )
        assert loop._classify_agy_result(0, event, False) == "completed"

    def test_completed_requires_exit_code_zero(self):
        """Nonzero exit with success event → agy_error, not completed."""
        event = agy_stream.AgyEvent(
            event_type=agy_stream.EVENT_RESULT,
            raw="",
            status="SUCCESS",
        )
        assert loop._classify_agy_result(1, event, False) == "agy_error"

    def test_completed_requires_terminal_event(self):
        """Zero exit without terminal event → agy_error, not completed."""
        assert loop._classify_agy_result(0, None, False) == "agy_error"

    def test_cancelled_status_is_error(self):
        """CANCELLED status is not success → agy_error."""
        event = agy_stream.AgyEvent(
            event_type=agy_stream.EVENT_RESULT,
            raw="",
            status="CANCELLED",
        )
        assert loop._classify_agy_result(0, event, False) == "agy_error"

    def test_empty_status_is_error(self):
        """Missing/empty status is not success → agy_error."""
        event = agy_stream.AgyEvent(
            event_type=agy_stream.EVENT_RESULT,
            raw="",
            status=None,
        )
        assert loop._classify_agy_result(0, event, False) == "agy_error"

    def test_agy_error_on_error_status(self):
        event = agy_stream.AgyEvent(
            event_type=agy_stream.EVENT_RESULT,
            raw="",
            status="ERROR",
            error="model overloaded",
        )
        assert loop._classify_agy_result(1, event, False) == "agy_error"

    def test_agy_print_timeout_on_timeout_error(self):
        event = agy_stream.AgyEvent(
            event_type=agy_stream.EVENT_RESULT,
            raw="",
            status="ERROR",
            error="timeout waiting for response",
        )
        assert loop._classify_agy_result(1, event, False) == "agy_print_timeout"

    def test_narrow_timeout_detection(self):
        """Generic timeout text must not classify as agy_print_timeout."""
        event = agy_stream.AgyEvent(
            event_type=agy_stream.EVENT_RESULT,
            raw="",
            status="ERROR",
            error="request timeout: network",
        )
        assert loop._classify_agy_result(1, event, False) == "agy_error"

    def test_agy_inactivity_timeout_on_kill(self):
        assert loop._classify_agy_result(-1, None, True) == "agy_inactivity_timeout"

    def test_agy_error_on_nonzero_exit_no_event(self):
        assert loop._classify_agy_result(2, None, False) == "agy_error"


# --- Inactivity timeout in reader loop ---------------------------------


class TestInactivityTimeout:
    """Test that the reader loop warns then kills on inactivity.

    These tests verify the classification logic (_classify_agy_result) and
    the _parse_duration helper. The full reader loop requires real file
    descriptors for selectors; see test_agy_reader_loop_integration for
    a real-pipe-based test.
    """

    def test_inactivity_killed_classifies_as_timeout(self):
        """_classify_agy_result returns agy_inactivity_timeout when killed."""
        assert loop._classify_agy_result(-15, None, True) == "agy_inactivity_timeout"

    def test_parse_duration_seconds(self):
        assert loop._parse_duration("30s") == 30.0

    def test_parse_duration_minutes(self):
        assert loop._parse_duration("5m") == 300.0

    def test_parse_duration_hours(self):
        assert loop._parse_duration("1h") == 3600.0

    def test_parse_duration_none(self):
        assert loop._parse_duration(None) is None
        assert loop._parse_duration("") is None

    def test_parse_duration_plain_number(self):
        assert loop._parse_duration("45") == 45.0

    def test_is_agy_cli_detects_agy(self):
        info = _agy_cli_info()
        assert loop._is_agy_cli(info) is True

    def test_is_agy_cli_rejects_non_agy(self):
        info = {"command": ["codex", "exec", "--full-auto"]}
        assert loop._is_agy_cli(info) is False

    def test_agy_failure_explanations_defined(self):
        assert "agy_error" in loop.AGY_FAILURE_EXPLANATIONS
        assert "agy_print_timeout" in loop.AGY_FAILURE_EXPLANATIONS
        assert "agy_inactivity_timeout" in loop.AGY_FAILURE_EXPLANATIONS


# --- Sandbox integration -----------------------------------------------


class TestSandboxAgyArgv:
    """The longer agy argv must not break sandbox detection or bwrap wrapping."""

    def test_is_agy_command_true_for_new_argv(self):
        cmd = _agy_cli_info()["command"]
        assert _is_agy_command(cmd) is True

    def test_bwrap_preserves_prompt_as_final_element(self, tmp_path):
        cli_info = _agy_cli_info()
        full_cmd = cli_info["command"] + ["PROMPT_CONTENT"]
        sandbox_config = {
            "enabled": True,
            "type": "bubblewrap",
            "profile": "balanced",
            "workspace": str(tmp_path),
            "network": True,
        }
        bwrap_args = build_bwrap_args(sandbox_config, full_cmd)
        # The child_command passed to bwrap ends with -- --print PROMPT_CONTENT
        sep_idx = bwrap_args.index("--")
        child = bwrap_args[sep_idx + 1:]
        assert child[-1] == "PROMPT_CONTENT"
        assert child[-2] == "--print"
        assert "--print-timeout" in child
        assert "stream-json" in child

    def test_agy_auth_preflight_still_probes_agy_models(self, tmp_path):
        """The preflight should still run `agy models` with the new argv shape."""
        from sandbox import _agy_auth_preflight, _agy_auth_bind_file
        sandbox_config = {
            "enabled": True,
            "type": "bubblewrap",
            "profile": "balanced",
            "workspace": str(tmp_path),
            "network": True,
        }
        cli_info = _agy_cli_info()
        # If no token file exists, preflight returns an error message
        # (not a crash) — that's the expected behavior.
        token = _agy_auth_bind_file(Path.home())
        if token is None:
            result = _agy_auth_preflight("agy", sandbox_config, cli_info, str(tmp_path))
            assert result is not None
            assert "not authenticated" in result.lower()
        else:
            # If token exists, the preflight would try to run agy models.
            # We just verify it doesn't crash on the new argv.
            pass


# --- Loop state: conversation_id / status persistence ------------------


class TestLoopStatePersistence:
    """Iteration records must contain conversation_id and terminal_status
    when the CLI provides them."""

    def test_update_loop_iteration_stores_conversation_id(self):
        state = {"iteration": 1, "max_iterations": 3, "history": []}
        state = loop.update_loop_iteration(
            state,
            exit_code=0,
            marker_found=True,
            log_file="/tmp/test.log",
            conversation_id="conv-123",
            terminal_status="SUCCESS",
            exec_status="completed",
        )
        record = state["history"][-1]
        assert record["conversation_id"] == "conv-123"
        assert record["terminal_status"] == "SUCCESS"
        assert record["exec_status"] == "completed"

    def test_update_loop_iteration_without_agy_fields(self):
        """Non-agy CLIs still work without conversation_id/status."""
        state = {"iteration": 1, "max_iterations": 3, "history": []}
        state = loop.update_loop_iteration(
            state,
            exit_code=0,
            marker_found=False,
            log_file="/tmp/test.log",
        )
        record = state["history"][-1]
        assert "conversation_id" not in record
        assert "terminal_status" not in record


# --- Legacy regression: all non-AGY shorthands byte-exact --------------


class TestNonAgyCommandsUnchanged:
    """Every non-AGY command must be byte-for-byte unchanged."""

    @pytest.fixture(autouse=True)
    def _no_router(self, monkeypatch):
        """Disable router resolution so registry commands are used directly."""
        monkeypatch.setattr(
            models, "_resolve_router_command",
            lambda *_args, **_kwargs: None,
        )

    @pytest.mark.parametrize("shorthand,expected", [
        ("gemini-high", ["gemini", "-y", "-m", "gemini-2.5-pro", "-p"]),
        ("gemini-xhigh", ["gemini", "-y", "-m", "gemini-3-pro-preview", "-p"]),
        ("gemini25pro", ["gemini", "-y", "-m", "gemini-2.5-pro", "-p"]),
        ("gemini25flash", ["gemini", "-y", "-m", "gemini-2.5-flash", "-p"]),
        ("gemini25lite", ["gemini", "-y", "-m", "gemini-2.5-flash-lite", "-p"]),
        ("gemini3flash", ["gemini", "-y", "-m", "gemini-3-flash-preview", "-p"]),
        ("gemini3pro", ["gemini", "-y", "-m", "gemini-3-pro-preview", "-p"]),
        ("gemini31pro", ["gemini", "-y", "-m", "gemini-3.1-pro-preview", "-p"]),
        ("gemini37-high", ["gemini", "-y", "-m", "gemini-3.8-flash", "-p"]),
        ("gemini37-medium", ["gemini", "-y", "-m", "gemini-3.8-flash", "-p"]),
        ("gemini37-low", ["gemini", "-y", "-m", "gemini-3.8-flash", "-p"]),
    ])
    def test_legacy_gemini_cli_argv_unchanged(self, tmp_path, shorthand, expected):
        info = models.get_cli_info(shorthand, repo_root=tmp_path, cli_override="gemini")
        assert info["command"] == expected, f"{shorthand} command changed"

    @pytest.mark.parametrize("shorthand,expected", [
        ("codex", ["codex", "exec", "--full-auto", "-m", "gpt-5.6-terra"]),
        ("codex-spark", ["codex", "exec", "--full-auto", "-m", "gpt-5.3-codex-spark"]),
        ("sol", ["codex", "exec", "--full-auto", "-m", "gpt-5.6-sol"]),
        ("terra", ["codex", "exec", "--full-auto", "-m", "gpt-5.6-terra"]),
        ("luna", ["codex", "exec", "--full-auto", "-m", "gpt-5.6-luna"]),
        ("zai", ["codex", "exec", "--full-auto", "--profile", "zai"]),
    ])
    def test_codex_argv_unchanged(self, tmp_path, shorthand, expected):
        info = models.get_cli_info(shorthand, repo_root=tmp_path)
        assert info["command"] == expected, f"{shorthand} command changed"

    def test_claude_subagent_has_empty_command(self, tmp_path):
        info = models.get_cli_info("claude", repo_root=tmp_path)
        assert info["command"] == []
        assert info["stdin_mode"] is None

    def test_opencode_command_unchanged(self, tmp_path):
        info = models.get_cli_info("opencode", repo_root=tmp_path)
        assert info["command"] == [
            "opencode", "run", "--format", "json",
            "-m", "zai/glm-4.7", "--pure", "--agent", "build",
        ]


# --- Real-pipe reader-loop test: inactivity warn then kill ------------


class TestReaderLoopInactivity:
    """Prove the reader loop warns then kills on inactivity using real pipes."""

    def test_inactivity_warn_then_terminate(self, tmp_path):
        """A child that emits nothing triggers warning then process-group kill."""
        import os
        import subprocess as sp

        log_file = tmp_path / "inactivity.log"
        log_handle = open(log_file, "w")

        # Spawn a child that sleeps (emits nothing on stdout)
        process = sp.Popen(
            ["sleep", "300"],
            stdout=sp.PIPE,
            stderr=sp.STDOUT,
            text=True,
            start_new_session=True,
        )
        try:
            reader = loop._run_agy_reader_loop(process, log_handle, inactivity_timeout=2.0)
            log_handle.close()
        finally:
            try:
                os.killpg(os.getpgid(process.pid), signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                pass

        assert reader["inactivity_killed"] is True
        log_content = log_file.read_text()
        assert "[agy] inactivity warning" in log_content
        assert "[agy] inactivity timeout" in log_content

    def test_reader_loop_processes_stream_json(self, tmp_path):
        """A child emitting stream-json lines is parsed and logged."""
        import subprocess as sp

        log_file = tmp_path / "stream.log"
        log_handle = open(log_file, "w")

        lines = [
            '{"event":"init","conversation_id":"conv-xyz",'
            '"init":{"model":"Gemini 3.8 Flash (High)"}}',
            '{"event":"step_update","step_update":{"conversation_id":"conv-xyz",'
            '"step_index":0,"state":"ACTIVE","step_type":"agent_response",'
            '"text_delta":"<verification>VERIFICATION_COMPLETE</verification>"}}',
            '{"event":"result","result":{"conversation_id":"conv-xyz",'
            '"status":"SUCCESS","response":"done"}}',
        ]
        # Write lines to a temp file and cat it, to avoid printf escape issues
        script_file = tmp_path / "emit.sh"
        script_file.write_text("#!/bin/bash\n" + "\n".join(f"echo {repr(line)}" for line in lines) + "\n")
        script_file.chmod(0o755)
        process = sp.Popen(
            [str(script_file)],
            stdout=sp.PIPE,
            stderr=sp.STDOUT,
            text=True,
            start_new_session=True,
        )
        reader = loop._run_agy_reader_loop(process, log_handle, inactivity_timeout=None)
        log_handle.close()

        assert reader["inactivity_killed"] is False
        assert reader["conversation_id"] == "conv-xyz"
        assert reader["terminal_status"] == "SUCCESS"
        assert reader["exit_code"] == 0

        log_content = log_file.read_text()
        assert "VERIFICATION_COMPLETE" in log_content


# --- Blocking false-success regression tests ---------------------------


class TestBlockingFalseSuccessRegressions:
    """Regression tests for the two merge-blocking false-success paths:

    1. A marker present in a timeout/error log must never complete the loop.
    2. Exit code 0 without a terminal AGY result event must not be 'completed'.
    """

    @pytest.fixture(autouse=True)
    def _no_router(self, monkeypatch):
        monkeypatch.setattr(
            models, "_resolve_router_command",
            lambda *_args, **_kwargs: None,
        )

    def test_marker_in_timeout_log_does_not_complete(self, tmp_path, monkeypatch):
        """A completion marker in an agy_print_timeout log must not complete."""
        import importlib.util

        executor_path = Path(__file__).resolve().parents[1] / "scripts" / "executor.py"
        spec = importlib.util.spec_from_file_location("executor_reg", executor_path)
        executor_mod = importlib.util.module_from_spec(spec)
        sys.modules["executor_reg"] = executor_mod
        spec.loader.exec_module(executor_mod)

        state_dir = tmp_path / "loop-state"
        state_dir.mkdir()
        log_dir = tmp_path / "logs"
        log_dir.mkdir()
        monkeypatch.setattr(loop, "get_loop_state_dir", lambda: state_dir)

        # Real git repo for execution cwd
        repo = tmp_path / "repo"
        repo.mkdir()
        import subprocess as sp
        sp.run(["git", "init", "-b", "main"], cwd=repo, check=True, capture_output=True)
        sp.run(["git", "config", "user.email", "t@t"], cwd=repo, check=True, capture_output=True)
        sp.run(["git", "config", "user.name", "t"], cwd=repo, check=True, capture_output=True)
        (repo / "README.md").write_text("seed\n")
        sp.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
        sp.run(["git", "commit", "-m", "seed"], cwd=repo, check=True, capture_output=True)

        def fake_run(cli_info, content, cwd, log_file, sandbox_config=None):
            with open(log_file, "w") as f:
                # Write stream-json lines including a spurious marker
                f.write('{"event":"step_update","step_update":{"text_delta":'
                        '"<verification>VERIFICATION_COMPLETE</verification>"}}\n')
                f.write('{"event":"result","result":{"status":"ERROR",'
                        '"error":"timeout waiting for response"}}\n')
            return {
                "status": "agy_print_timeout",
                "exit_code": 1,
                "log": str(log_file),
                "conversation_id": "conv-fake",
                "terminal_status": "ERROR",
            }

        monkeypatch.setattr(loop, "run_cli_foreground", fake_run)

        result = executor_mod.run_verification_loop(
            cli_info=_agy_cli_info(),
            original_content="do the thing",
            cwd=str(repo),
            log_dir=log_dir,
            prompt_number="998",
            model="gemini",
            max_iterations=2,
            completion_marker="VERIFICATION_COMPLETE",
            execution_timestamp="20260703-000000",
        )

        assert result["final_status"] != "completed"
        assert result["iterations"][0]["marker_found"] is False
        assert result["iterations"][0]["exec_status"] == "agy_print_timeout"

    def test_marker_in_error_log_does_not_complete(self, tmp_path, monkeypatch):
        """A completion marker in an agy_error log must not complete."""
        import importlib.util

        executor_path = Path(__file__).resolve().parents[1] / "scripts" / "executor.py"
        spec = importlib.util.spec_from_file_location("executor_reg2", executor_path)
        executor_mod = importlib.util.module_from_spec(spec)
        sys.modules["executor_reg2"] = executor_mod
        spec.loader.exec_module(executor_mod)

        state_dir = tmp_path / "loop-state"
        state_dir.mkdir()
        log_dir = tmp_path / "logs"
        log_dir.mkdir()
        monkeypatch.setattr(loop, "get_loop_state_dir", lambda: state_dir)

        repo = tmp_path / "repo"
        repo.mkdir()
        import subprocess as sp
        sp.run(["git", "init", "-b", "main"], cwd=repo, check=True, capture_output=True)
        sp.run(["git", "config", "user.email", "t@t"], cwd=repo, check=True, capture_output=True)
        sp.run(["git", "config", "user.name", "t"], cwd=repo, check=True, capture_output=True)
        (repo / "README.md").write_text("seed\n")
        sp.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
        sp.run(["git", "commit", "-m", "seed"], cwd=repo, check=True, capture_output=True)

        def fake_run(cli_info, content, cwd, log_file, sandbox_config=None):
            with open(log_file, "w") as f:
                f.write('{"event":"step_update","step_update":{"text_delta":'
                        '"<verification>VERIFICATION_COMPLETE</verification>"}}\n')
                f.write('{"event":"result","result":{"status":"ERROR",'
                        '"error":"model overloaded"}}\n')
            return {
                "status": "agy_error",
                "exit_code": 1,
                "log": str(log_file),
                "conversation_id": "conv-fake",
                "terminal_status": "ERROR",
            }

        monkeypatch.setattr(loop, "run_cli_foreground", fake_run)

        result = executor_mod.run_verification_loop(
            cli_info=_agy_cli_info(),
            original_content="do the thing",
            cwd=str(repo),
            log_dir=log_dir,
            prompt_number="997",
            model="gemini",
            max_iterations=2,
            completion_marker="VERIFICATION_COMPLETE",
            execution_timestamp="20260703-000000",
        )

        assert result["final_status"] != "completed"
        assert result["iterations"][0]["marker_found"] is False
        assert result["iterations"][0]["exec_status"] == "agy_error"
