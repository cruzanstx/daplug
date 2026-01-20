import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.append(str(SCRIPT_DIR))

from plugins import discover_plugins, get_plugin  # noqa: E402


def test_discover_plugins_has_tier1():
    names = [p.name for p in discover_plugins()]
    assert "claude" in names
    assert "codex" in names
    assert "gemini" in names
    assert "opencode" in names


def test_get_plugin_by_name():
    plugin = get_plugin("codex")
    assert plugin is not None
    assert plugin.name == "codex"


def test_get_plugin_unknown_returns_none():
    assert get_plugin("does-not-exist") is None


@pytest.mark.parametrize(
    "name,expected_path_suffix",
    [
        ("claude", ".claude/settings.json"),
        ("codex", ".codex/config.toml"),
        ("gemini", ".config/gemini/config.json"),
        ("opencode", ".config/opencode/opencode.json"),
    ],
)
def test_plugin_config_paths_include_expected(name, expected_path_suffix):
    plugin = get_plugin(name)
    assert plugin is not None
    paths = [str(p) for p in plugin.get_config_paths()]
    assert any(p.endswith(expected_path_suffix) for p in paths)


def test_detect_installation_uses_shutil_which(monkeypatch):
    plugin = get_plugin("codex")
    assert plugin is not None

    import plugins.base as base_mod

    def fake_which(name: str):
        assert name == "codex"
        return "/usr/local/bin/codex"

    monkeypatch.setattr(base_mod.shutil, "which", fake_which)
    installed, exe = plugin.detect_installation()
    assert installed is True
    assert exe == "/usr/local/bin/codex"


def test_get_version_runs_subprocess(monkeypatch):
    plugin = get_plugin("codex")
    assert plugin is not None

    import plugins.base as base_mod

    monkeypatch.setattr(base_mod.shutil, "which", lambda _name: "/usr/local/bin/codex")

    def fake_run(cmd, capture_output, text, check, cwd, timeout):
        assert cmd[0] in {"codex", "/usr/local/bin/codex"}
        assert "--version" in cmd
        return subprocess.CompletedProcess(cmd, 0, stdout="codex 1.2.3\n", stderr="")

    monkeypatch.setattr(base_mod.subprocess, "run", fake_run)
    assert plugin.get_version() == "codex 1.2.3"
