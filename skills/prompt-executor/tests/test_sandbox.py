import argparse
import sys
from pathlib import Path

import pytest

SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.append(str(SCRIPT_DIR))

import executor  # noqa: E402
import loop  # noqa: E402


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
    assert "--proc" in cmd
    assert "/proc" in cmd
    assert "--tmpfs" in cmd
    assert "--" in cmd
    assert cmd[-4:] == ["codex", "exec", "--full-auto", "-"]

    for marker in expected_contains:
        assert marker in joined
    for marker in expected_absent:
        assert marker not in joined


def test_build_bwrap_args_binds_nvm_cli_runtime(tmp_path, monkeypatch):
    home = tmp_path / "home"
    local_bin = home / ".local" / "bin"
    nvm_version = home / ".nvm" / "versions" / "node" / "v24.9.0"
    target = nvm_version / "lib" / "node_modules" / "opencode-ai" / "bin" / "opencode.exe"
    target.parent.mkdir(parents=True)
    target.write_text("binary")
    local_bin.mkdir(parents=True)
    symlink = local_bin / "opencode"
    symlink.symlink_to(target)

    monkeypatch.setattr(executor.Path, "home", lambda: home)
    monkeypatch.setattr(executor.shutil, "which", lambda name: str(symlink) if name == "opencode" else None)

    config = {
        "enabled": True,
        "type": "bubblewrap",
        "profile": "strict",
        "workspace": str(tmp_path),
        "network": False,
    }
    cmd = executor.build_bwrap_args(config, ["opencode", "run"])

    assert ["--ro-bind", str(local_bin), str(local_bin)] in [cmd[i : i + 3] for i in range(len(cmd) - 2)]
    assert ["--ro-bind", str(nvm_version), str(nvm_version)] in [cmd[i : i + 3] for i in range(len(cmd) - 2)]


def test_build_bwrap_args_binds_bun_cli_runtime(tmp_path, monkeypatch):
    home = tmp_path / "home"
    bun_global = home / ".bun" / "install" / "global"
    bun_bin = home / ".bun" / "bin"
    target = bun_global / "node_modules" / "@openai" / "codex" / "bin" / "codex.js"
    target.parent.mkdir(parents=True)
    target.write_text("#!/usr/bin/env node")
    bun_bin.mkdir(parents=True)
    source = bun_bin / "codex"
    source.symlink_to(target)

    monkeypatch.setattr(executor.Path, "home", lambda: home)
    monkeypatch.setattr(executor.shutil, "which", lambda name: str(source) if name == "codex" else None)

    config = {
        "enabled": True,
        "type": "bubblewrap",
        "profile": "strict",
        "workspace": str(tmp_path),
        "network": False,
    }
    cmd = executor.build_bwrap_args(config, ["codex", "exec", "-"])

    assert ["--ro-bind", str(source.parent), str(source.parent)] in [cmd[i : i + 3] for i in range(len(cmd) - 2)]
    assert ["--ro-bind", str(bun_bin), str(bun_bin)] in [cmd[i : i + 3] for i in range(len(cmd) - 2)]
    assert ["--ro-bind", str(bun_global), str(bun_global)] in [cmd[i : i + 3] for i in range(len(cmd) - 2)]


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


def test_build_bwrap_args_passes_extra_env_through_clearenv(tmp_path, monkeypatch):
    monkeypatch.setattr(executor.Path, "home", lambda: tmp_path)
    config = {
        "enabled": True,
        "type": "bubblewrap",
        "profile": "balanced",
        "workspace": str(tmp_path),
        "network": True,
    }
    cmd = executor.build_bwrap_args(
        config, ["opencode", "run"], extra_env={"SYNTHETIC_API_KEY": "sk-test"}
    )

    triples = [cmd[i : i + 3] for i in range(len(cmd) - 2)]
    assert "--clearenv" in cmd
    assert ["--setenv", "SYNTHETIC_API_KEY", "sk-test"] in triples


def test_build_bwrap_args_dev_profile_skips_extra_env(tmp_path, monkeypatch):
    monkeypatch.setattr(executor.Path, "home", lambda: tmp_path)
    config = {
        "enabled": True,
        "type": "bubblewrap",
        "profile": "dev",
        "workspace": str(tmp_path),
        "network": True,
    }
    cmd = executor.build_bwrap_args(
        config, ["opencode", "run"], extra_env={"SYNTHETIC_API_KEY": "sk-test"}
    )

    # dev profile inherits the full environment, so no --clearenv/--setenv needed
    assert "--clearenv" not in cmd
    assert "sk-test" not in cmd


def test_sandbox_passthrough_env_collects_credentials(monkeypatch):
    monkeypatch.setenv("SYNTHETIC_API_KEY", "sk-from-env")
    monkeypatch.delenv("LMSTUDIO_API_KEY", raising=False)

    extra = executor._sandbox_passthrough_env({"env": {"LMSTUDIO_API_KEY": "lm-studio"}})

    assert extra == {"LMSTUDIO_API_KEY": "lm-studio", "SYNTHETIC_API_KEY": "sk-from-env"}


def test_sandbox_passthrough_env_empty_when_nothing_set(monkeypatch):
    for key in executor.SANDBOX_ENV_PASSTHROUGH:
        monkeypatch.delenv(key, raising=False)

    assert executor._sandbox_passthrough_env({"env": {}}) == {}


@pytest.fixture()
def preflight_env(tmp_path, monkeypatch):
    executor._SANDBOX_PREFLIGHT_CACHE.clear()
    monkeypatch.setattr(executor.Path, "home", lambda: tmp_path)
    yield {
        "cli_info": {"command": ["opencode", "run"], "env": {}},
        "sandbox_config": {
            "enabled": True,
            "type": "bubblewrap",
            "profile": "balanced",
            "workspace": str(tmp_path),
            "network": True,
        },
        "cwd": str(tmp_path),
    }
    executor._SANDBOX_PREFLIGHT_CACHE.clear()


class _ProbeResult:
    def __init__(self, returncode, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def test_sandbox_preflight_passes_on_zero_exit(preflight_env, monkeypatch):
    monkeypatch.setattr(
        executor.subprocess, "run", lambda *a, **kw: _ProbeResult(0, stdout="1.2.3")
    )
    assert executor.sandbox_preflight(**preflight_env) is None


def test_sandbox_preflight_fails_on_nonzero_exit(preflight_env, monkeypatch):
    monkeypatch.setattr(
        executor.subprocess,
        "run",
        lambda *a, **kw: _ProbeResult(127, stderr="bwrap: execvp opencode: No such file or directory"),
    )
    error = executor.sandbox_preflight(**preflight_env)

    assert error is not None
    assert "preflight probe 'opencode --version'" in error
    assert "exit 127" in error
    assert "No such file or directory" in error
    assert "--no-sandbox" in error  # standard sandbox error hint


def test_sandbox_preflight_caches_per_sandbox_shape(preflight_env, monkeypatch):
    calls = []

    def fake_run(*a, **kw):
        calls.append(a)
        return _ProbeResult(0)

    monkeypatch.setattr(executor.subprocess, "run", fake_run)
    executor.sandbox_preflight(**preflight_env)
    executor.sandbox_preflight(**preflight_env)

    assert len(calls) == 1


def test_sandbox_preflight_skipped_when_sandbox_disabled(preflight_env, monkeypatch):
    def boom(*a, **kw):
        raise AssertionError("probe must not run when sandbox is disabled")

    monkeypatch.setattr(executor.subprocess, "run", boom)
    assert executor.sandbox_preflight(preflight_env["cli_info"], None, preflight_env["cwd"]) is None
    assert (
        executor.sandbox_preflight(
            preflight_env["cli_info"],
            {**preflight_env["sandbox_config"], "enabled": False},
            preflight_env["cwd"],
        )
        is None
    )


def test_run_cli_foreground_aborts_on_preflight_failure(tmp_path, monkeypatch):
    monkeypatch.setattr(loop, "check_bwrap_available", lambda: True)
    monkeypatch.setattr(loop, "sandbox_preflight", lambda *a, **kw: "probe failed")

    def boom(*a, **kw):
        raise AssertionError("CLI must not launch when preflight fails")

    monkeypatch.setattr(executor.subprocess, "Popen", boom)

    result = executor.run_cli_foreground(
        {"command": ["opencode", "run"], "env": {}, "stdin_mode": "arg"},
        "hello",
        str(tmp_path),
        tmp_path / "preflight.log",
        sandbox_config={
            "enabled": True,
            "type": "bubblewrap",
            "profile": "balanced",
            "workspace": str(tmp_path),
            "network": True,
        },
    )

    assert result["status"] == "error"
    assert result["error"] == "probe failed"


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

    monkeypatch.setattr(loop, "check_bwrap_available", lambda: True)
    monkeypatch.setattr(loop, "sandbox_preflight", lambda *a, **kw: None)
    monkeypatch.setattr(
        loop,
        "build_bwrap_args",
        lambda config, child, extra_env=None: ["bwrap", "--unshare-all", "--", *child],
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
