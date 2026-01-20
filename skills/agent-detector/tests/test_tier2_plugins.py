import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.append(str(SCRIPT_DIR))

from plugins import discover_plugins, get_plugin  # noqa: E402


def test_discover_plugins_has_tier2():
    names = [p.name for p in discover_plugins()]
    assert "aider" in names
    assert "ghcopilot" in names
    assert "goose" in names


@pytest.mark.parametrize(
    "name,exe,expected_path",
    [
        ("goose", "goose", "/usr/local/bin/goose"),
        ("aider", "aider", "/usr/local/bin/aider"),
    ],
)
def test_tier2_detect_installation_uses_shutil_which(monkeypatch, name, exe, expected_path):
    plugin = get_plugin(name)
    assert plugin is not None

    import plugins.base as base_mod

    def fake_which(requested: str):
        assert requested == exe
        return expected_path

    monkeypatch.setattr(base_mod.shutil, "which", fake_which)

    installed, path = plugin.detect_installation()
    assert installed is True
    assert path == expected_path


def test_ghcopilot_detect_installation_requires_extension(monkeypatch):
    plugin = get_plugin("ghcopilot")
    assert plugin is not None

    import plugins.base as base_mod

    monkeypatch.setattr(base_mod.shutil, "which", lambda name: "/usr/bin/gh" if name == "gh" else None)

    def fake_run(cmd, capture_output, text, check, cwd, timeout):
        assert cmd[0] in {"gh", "/usr/bin/gh"}
        assert cmd[1:3] == ["extension", "list"]
        return subprocess.CompletedProcess(cmd, 0, stdout="github/gh-copilot\n", stderr="")

    monkeypatch.setattr(base_mod.subprocess, "run", fake_run)

    installed, exe = plugin.detect_installation()
    assert installed is True
    assert exe == "/usr/bin/gh"


@pytest.mark.parametrize("name", ["goose", "aider", "ghcopilot"])
def test_tier2_plugins_list_models(name):
    plugin = get_plugin(name)
    assert plugin is not None
    models = plugin.get_available_models()
    assert models
    assert all(m.id and m.display_name and m.provider for m in models)


def test_goose_build_command():
    plugin = get_plugin("goose")
    assert plugin is not None
    cmd = plugin.build_command(model="openai:gpt-4o", prompt_file=Path("prompt.txt"), cwd=Path("."))
    assert cmd == ["goose", "session"]


def test_aider_build_command_reads_prompt_and_sets_model(tmp_path: Path):
    plugin = get_plugin("aider")
    assert plugin is not None
    prompt = tmp_path / "prompt.txt"
    prompt.write_text("hello from aider\n", encoding="utf-8")
    cmd = plugin.build_command(model="openai:gpt-4o", prompt_file=prompt, cwd=tmp_path)
    assert cmd[:4] == ["aider", "--message", "hello from aider\n", "--yes"]
    assert cmd[4:] == ["--model", "gpt-4o"]


def test_ghcopilot_build_command():
    plugin = get_plugin("ghcopilot")
    assert plugin is not None
    cmd = plugin.build_command(model="github:copilot", prompt_file=Path("prompt.txt"), cwd=Path("."))
    assert cmd == ["gh", "copilot", "suggest"]

