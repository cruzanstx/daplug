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
    assert "agy" in names
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
        ("agy", ".gemini/antigravity-cli/settings.json"),
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


def test_agy_plugin_builds_argv_print_command(tmp_path):
    plugin = get_plugin("agy")
    assert plugin is not None

    prompt_file = tmp_path / "prompt.md"
    prompt_file.write_text("Say only: ok", encoding="utf-8")

    assert plugin.build_command("google:gemini-3.1-pro-preview", prompt_file, tmp_path) == [
        "agy",
        "--model",
        "Gemini 3.1 Pro (High)",
        "--print",
        "Say only: ok",
    ]
    assert plugin.build_command("google:gemini-3-flash-preview", prompt_file, tmp_path)[:4] == [
        "agy",
        "--model",
        "Gemini 3.5 Flash (Medium)",
        "--print",
    ]


def test_agy_plugin_version_command():
    plugin = get_plugin("agy")
    assert plugin is not None
    assert plugin.version_cmd == ["agy", "--version"]
    assert plugin.get_supported_providers() == ["google"]


def test_agy_plugin_reports_error_when_required_flags_missing(monkeypatch):
    plugin = get_plugin("agy")
    assert plugin is not None

    import plugins.agy as agy_mod
    import plugins.base as base_mod

    monkeypatch.setattr(base_mod.shutil, "which", lambda name: "/usr/local/bin/agy" if name == "agy" else None)
    monkeypatch.setattr(agy_mod, "_run_command", lambda _cmd: "Usage: agy --print <prompt>")

    issues = plugin.detect_issues()
    assert any(
        issue.severity == "error" and issue.type == "unsupported_command_flags"
        for issue in issues
    )
