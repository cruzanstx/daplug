import importlib.util
import tempfile
import unittest
from pathlib import Path


def _load_executor_module():
    executor_path = Path(__file__).resolve().parent / "executor.py"
    spec = importlib.util.spec_from_file_location("prompt_executor", executor_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("Failed to load executor module spec")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


executor = _load_executor_module()


class TestCompletionMarkerDetection(unittest.TestCase):
    def _write_temp_log(self, text: str) -> Path:
        handle = tempfile.NamedTemporaryFile("w", delete=False, encoding="utf-8")
        try:
            handle.write(text)
            handle.flush()
            return Path(handle.name)
        finally:
            handle.close()

    def test_does_not_false_positive_on_prompt_echo(self):
        wrapped = executor.wrap_prompt_with_verification_protocol(
            content="Do a thing.",
            iteration=1,
            max_iterations=3,
            completion_marker=executor.DEFAULT_COMPLETION_MARKER,
            worktree_path=None,
            branch_name=None,
            history=[],
        )
        # Simulate a CLI that prints the full prompt into the log, but the model does not output a marker.
        log_path = self._write_temp_log(wrapped + "\nAssistant: I worked on it.\n")
        try:
            found, retry_reason = executor.check_completion_marker(log_path, executor.DEFAULT_COMPLETION_MARKER)
            self.assertFalse(found)
            self.assertIsNone(retry_reason)
        finally:
            log_path.unlink(missing_ok=True)

    def test_detects_completion_marker_after_sentinel(self):
        wrapped = executor.wrap_prompt_with_verification_protocol(
            content="Do a thing.",
            iteration=1,
            max_iterations=3,
            completion_marker=executor.DEFAULT_COMPLETION_MARKER,
            history=[],
        )
        log_text = wrapped + "\nAll done.\n<verification>VERIFICATION_COMPLETE</verification>\n"
        log_path = self._write_temp_log(log_text)
        try:
            found, retry_reason = executor.check_completion_marker(log_path, executor.DEFAULT_COMPLETION_MARKER)
            self.assertTrue(found)
            self.assertIsNone(retry_reason)
        finally:
            log_path.unlink(missing_ok=True)

    def test_detects_retry_marker_after_sentinel(self):
        wrapped = executor.wrap_prompt_with_verification_protocol(
            content="Do a thing.",
            iteration=1,
            max_iterations=3,
            completion_marker=executor.DEFAULT_COMPLETION_MARKER,
            history=[],
        )
        log_text = wrapped + "\nStill failing.\n<verification>NEEDS_RETRY: tests failing</verification>\n"
        log_path = self._write_temp_log(log_text)
        try:
            found, retry_reason = executor.check_completion_marker(log_path, executor.DEFAULT_COMPLETION_MARKER)
            self.assertFalse(found)
            self.assertEqual(retry_reason, "tests failing")
        finally:
            log_path.unlink(missing_ok=True)

    def test_backward_compat_fallback_without_sentinel(self):
        # Older logs may include </verification_protocol> but not the sentinel.
        log_text = (
            "<verification_protocol>\n"
            "example <verification>VERIFICATION_COMPLETE</verification>\n"
            "</verification_protocol>\n"
            "Assistant output:\n"
            "<verification>VERIFICATION_COMPLETE</verification>\n"
        )
        log_path = self._write_temp_log(log_text)
        try:
            found, retry_reason = executor.check_completion_marker(log_path, executor.DEFAULT_COMPLETION_MARKER)
            self.assertTrue(found)
            self.assertIsNone(retry_reason)
        finally:
            log_path.unlink(missing_ok=True)

    def test_detects_marker_when_prompt_not_echoed(self):
        # Some CLIs do not print the prompt at all; marker must still be detected.
        log_text = "Assistant output:\n<verification>VERIFICATION_COMPLETE</verification>\n"
        log_path = self._write_temp_log(log_text)
        try:
            found, retry_reason = executor.check_completion_marker(log_path, executor.DEFAULT_COMPLETION_MARKER)
            self.assertTrue(found)
            self.assertIsNone(retry_reason)
        finally:
            log_path.unlink(missing_ok=True)


class TestGetCliInfo(unittest.TestCase):
    """Tests for get_cli_info() model configuration."""

    def test_opencode_model_exists(self):
        """Verify opencode model is configured."""
        info = executor.get_cli_info("opencode")
        self.assertEqual(info["command"], ["opencode", "run", "--format", "json", "-m", "zai/glm-4.7"])
        self.assertEqual(info["stdin_mode"], "arg")
        self.assertFalse(info.get("needs_pty", False))

    def test_opencode_does_not_need_pty_flag(self):
        """Verify opencode does not require PTY when using JSON output."""
        info = executor.get_cli_info("opencode")
        self.assertFalse(info.get("needs_pty", False), "opencode should not need PTY")

    def test_codex_models_no_pty(self):
        """Verify codex models don't require PTY."""
        for model in ["codex", "codex-high", "codex-xhigh", "zai"]:
            info = executor.get_cli_info(model)
            self.assertFalse(info.get("needs_pty", False), f"{model} should not need PTY")

    def test_gemini_models_no_pty(self):
        """Verify gemini models don't require PTY."""
        for model in ["gemini", "gemini-high", "gemini-xhigh"]:
            info = executor.get_cli_info(model)
            self.assertFalse(info.get("needs_pty", False), f"{model} should not need PTY")

    def test_all_models_have_required_keys(self):
        """Verify all models have required configuration keys."""
        models = [
            "claude", "codex", "codex-high", "codex-xhigh",
            "gpt52", "gpt52-high", "gpt52-xhigh",
            "gemini", "gemini-high", "gemini-xhigh",
            "zai", "opencode", "local", "qwen", "devstral"
        ]
        for model in models:
            info = executor.get_cli_info(model)
            self.assertIn("command", info, f"{model} missing 'command'")
            self.assertIn("display", info, f"{model} missing 'display'")
            self.assertIn("env", info, f"{model} missing 'env'")
            self.assertIn("stdin_mode", info, f"{model} missing 'stdin_mode'")


class TestPtyCommandWrapping(unittest.TestCase):
    """Tests for PTY command wrapping logic."""

    def test_pty_wrapper_builds_correct_command(self):
        """Verify PTY wrapper uses script command correctly."""
        import shlex

        # Simulate what run_cli does for needs_pty=True
        base_cmd = ["opencode", "run", "-m", "zai/glm-4.7"]
        content = "Say hello"
        full_cmd = base_cmd + [content]

        # Build wrapped command
        cmd_str = " ".join(shlex.quote(arg) for arg in full_cmd)
        wrapped_cmd = ["script", "-q", "-c", cmd_str, "/dev/null"]

        self.assertEqual(wrapped_cmd[0], "script")
        self.assertEqual(wrapped_cmd[1], "-q")
        self.assertEqual(wrapped_cmd[2], "-c")
        self.assertIn("opencode", wrapped_cmd[3])
        self.assertIn("zai/glm-4.7", wrapped_cmd[3])
        self.assertEqual(wrapped_cmd[4], "/dev/null")

    def test_pty_wrapper_handles_special_characters(self):
        """Verify PTY wrapper properly escapes special characters."""
        import shlex

        base_cmd = ["opencode", "run", "-m", "zai/glm-4.7"]
        content = "Say 'hello world' with \"quotes\" and $variables"
        full_cmd = base_cmd + [content]

        cmd_str = " ".join(shlex.quote(arg) for arg in full_cmd)

        # Should be properly quoted
        self.assertIn("'hello world'", cmd_str)
        # The content should be escaped as a single argument
        self.assertNotIn("$variables", cmd_str.split("'")[0])  # $ should be inside quotes
