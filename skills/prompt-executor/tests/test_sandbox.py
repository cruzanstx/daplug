import argparse
import sys
from pathlib import Path

import pytest

SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.append(str(SCRIPT_DIR))

import executor  # noqa: E402


def _args(**overrides):
    base = {
        "sandbox": False,
        "sandbox_type": None,
        "no_sandbox": False,
        "sandbox_profile": "balanced",
        "sandbox_workspace": None,
        "sandbox_net": None,
    }
    base.update(overrides)
    return argparse.Namespace(**base)


def test_resolve_sandbox_config_defaults_disabled(tmp_path):
    config = executor.resolve_sandbox_config("linux", _args(), str(tmp_path))

    assert config["enabled"] is False
    assert config["type"] is None
    assert config["profile"] == "balanced"
    assert config["workspace"] == str(tmp_path.resolve())
    assert config["network"] is True


def test_resolve_sandbox_config_linux_defaults_to_bwrap(tmp_path):
    config = executor.resolve_sandbox_config("linux", _args(sandbox=True), str(tmp_path))

    assert config["enabled"] is True
    assert config["type"] == "bubblewrap"
    assert config["profile"] == "balanced"
    assert config["workspace"] == str(tmp_path.resolve())
    assert config["network"] is True


def test_resolve_sandbox_config_conflicting_flags_raise(tmp_path):
    with pytest.raises(ValueError, match="Cannot pass both --sandbox and --no-sandbox"):
        executor.resolve_sandbox_config("linux", _args(sandbox=True, no_sandbox=True), str(tmp_path))


def test_resolve_sandbox_config_type_without_enable_raises(tmp_path):
    with pytest.raises(ValueError, match="--sandbox-type requires sandboxing to be enabled"):
        executor.resolve_sandbox_config("linux", _args(sandbox_type="bubblewrap"), str(tmp_path))


def test_resolve_sandbox_config_non_linux_warns_and_disables(tmp_path, capsys):
    config = executor.resolve_sandbox_config("darwin", _args(sandbox=True), str(tmp_path))

    assert config["enabled"] is False
    assert config["type"] is None
    assert "sandbox requested on non-Linux" in capsys.readouterr().err


@pytest.mark.parametrize(
    "profile,expected_contains,expected_absent",
    [
        ("strict", [".local/share/opencode"], [".cache/opencode", ".config/opencode", "/go/pkg/mod", ".npm"]),
        ("balanced", [".local/share/opencode", ".cache/opencode", ".config/opencode"], ["/go/pkg/mod", ".npm"]),
        ("dev", [".local/share/opencode", ".cache/opencode", ".config/opencode", "/go/pkg/mod", ".npm"], []),
    ],
)
def test_build_bwrap_args_profiles(profile, expected_contains, expected_absent, tmp_path, monkeypatch):
    monkeypatch.setattr(executor.Path, "home", lambda: tmp_path)

    config = {
        "enabled": True,
        "type": "bubblewrap",
        "profile": profile,
        "workspace": str(tmp_path),
        "network": profile != "strict",
    }
    cmd = executor.build_bwrap_args(config, ["codex", "exec", "--full-auto", "-"])
    joined = " ".join(cmd)

    assert cmd[0] == "bwrap"
    assert "--unshare-all" in cmd
    assert "--new-session" in cmd
    assert "--die-with-parent" in cmd
    assert "--tmpfs" in cmd
    assert "--" in cmd
    assert cmd[-4:] == ["codex", "exec", "--full-auto", "-"]

    for marker in expected_contains:
        assert marker in joined
    for marker in expected_absent:
        assert marker not in joined


def test_build_bwrap_args_network_toggle(tmp_path, monkeypatch):
    monkeypatch.setattr(executor.Path, "home", lambda: tmp_path)
    base = {
        "enabled": True,
        "type": "bubblewrap",
        "profile": "strict",
        "workspace": str(tmp_path),
        "network": False,
    }
    cmd_net_off = executor.build_bwrap_args(base, ["opencode", "run"])
    assert "--share-net" not in cmd_net_off

    cmd_net_on = executor.build_bwrap_args({**base, "network": True}, ["opencode", "run"])
    assert "--share-net" in cmd_net_on


def test_check_bwrap_available_detection(monkeypatch):
    monkeypatch.setattr(executor.shutil, "which", lambda name: "/usr/bin/bwrap" if name == "bwrap" else None)
    assert executor.check_bwrap_available() is True

    monkeypatch.setattr(executor.shutil, "which", lambda _name: None)
    assert executor.check_bwrap_available() is False


def test_get_repo_root_falls_back_when_git_is_missing(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)

    def _missing_git(*_args, **_kwargs):
        raise FileNotFoundError("git")

    monkeypatch.setattr(executor.subprocess, "run", _missing_git)
    assert executor.get_repo_root() == tmp_path


def test_run_cli_wraps_with_bwrap_when_enabled(tmp_path, monkeypatch):
    captured = {}

    class _DummyStdin:
        def __init__(self):
            self.value = ""

        def write(self, text: str) -> None:
            self.value += text

        def close(self) -> None:
            return None

    class _DummyProc:
        pid = 999

        def __init__(self):
            self.stdin = _DummyStdin()

    def fake_popen(cmd, **_kwargs):
        captured["cmd"] = list(cmd)
        proc = _DummyProc()
        captured["stdin"] = proc.stdin
        return proc

    monkeypatch.setattr(executor, "check_bwrap_available", lambda: True)
    monkeypatch.setattr(
        executor,
        "build_bwrap_args",
        lambda config, child: ["bwrap", "--unshare-all", "--", *child],
    )
    monkeypatch.setattr(executor.subprocess, "Popen", fake_popen)

    log_file = tmp_path / "sandbox.log"
    cli_info = {"command": ["codex", "exec", "--full-auto"], "env": {}, "stdin_mode": "dash"}
    sandbox_config = {
        "enabled": True,
        "type": "bubblewrap",
        "profile": "balanced",
        "workspace": str(tmp_path),
        "network": True,
    }

    result = executor.run_cli(cli_info, "hello", str(tmp_path), log_file, sandbox_config=sandbox_config)
    assert result["status"] == "running"
    assert captured["cmd"][0] == "bwrap"
    assert captured["cmd"][-1] == "-"
    assert captured["stdin"].value == "hello"
