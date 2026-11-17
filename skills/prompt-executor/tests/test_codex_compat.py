"""Codex unattended-flag compatibility (codex-cli 0.167.0 removed --full-auto)."""

import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import models  # noqa: E402

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
