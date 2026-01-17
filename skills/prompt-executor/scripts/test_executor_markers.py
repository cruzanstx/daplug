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

