import argparse
import subprocess
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
    cmd = executor.build_bwrap_args(config, ["opencode", "run"])
    joined = " ".join(cmd)

    assert cmd[0] == "bwrap"
    assert "--unshare-all" in cmd
    assert "--new-session" in cmd
    assert "--die-with-parent" in cmd
    assert "--proc" in cmd
    assert "/proc" in cmd
    assert "--tmpfs" in cmd
    assert "--" in cmd
    assert cmd[-2:] == ["opencode", "run"]

    for marker in expected_contains:
        assert marker in joined
    for marker in expected_absent:
        assert marker not in joined


@pytest.mark.parametrize("profile", ["strict", "balanced", "dev"])
def test_build_bwrap_args_non_opencode_no_opencode_binds(profile, tmp_path, monkeypatch):
    """Codex/AGY/Claude children must not receive OpenCode writable state binds."""
    monkeypatch.setattr(executor.Path, "home", lambda: tmp_path)

    config = {
        "enabled": True,
        "type": "bubblewrap",
        "profile": profile,
        "workspace": str(tmp_path),
        "network": profile != "strict",
    }
    for child in (
        ["codex", "exec", "--full-auto", "-"],
        ["agy", "--model", "Gemini 3.7 Flash (High)", "--print"],
        ["claude", "--print"],
    ):
        cmd = executor.build_bwrap_args(config, child)
        joined = " ".join(cmd)
        assert ".local/share/opencode" not in joined
        assert ".cache/opencode" not in joined
        assert ".config/opencode" not in joined


def test_build_bwrap_args_opencode_identical_binds(tmp_path, monkeypatch):
    """OpenCode children must receive every writable bind the profile declares."""
    monkeypatch.setattr(executor.Path, "home", lambda: tmp_path)

    for profile, expected_writable in [
        ("strict", [".local/share/opencode"]),
        ("balanced", [".local/share/opencode", ".cache/opencode", ".config/opencode"]),
        ("dev", [".local/share/opencode", ".cache/opencode", ".config/opencode", "/go/pkg/mod", ".npm"]),
    ]:
        config = {
            "enabled": True,
            "type": "bubblewrap",
            "profile": profile,
            "workspace": str(tmp_path),
            "network": profile != "strict",
        }
        cmd = executor.build_bwrap_args(config, ["opencode", "run"])
        joined = " ".join(cmd)
        for marker in expected_writable:
            assert marker in joined, f"profile={profile}: missing {marker!r}"


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


# ---------------------------------------------------------------------------
# AGY token bind tests
# ---------------------------------------------------------------------------

def _make_fake_token(home: Path, contents: str = "fake-token-placeholder") -> Path:
    """Create a fake 0600 OAuth token under ``home`` and return its path."""
    token = home / ".gemini" / "antigravity-cli" / "antigravity-oauth-token"
    token.parent.mkdir(parents=True, exist_ok=True)
    token.write_text(contents)
    token.chmod(0o600)
    return token


@pytest.mark.parametrize("profile", ["strict", "balanced", "dev"])
def test_agy_gets_token_ro_bind_all_profiles(profile, tmp_path, monkeypatch):
    """AGY child gets --ro-bind of the token file in every profile."""
    monkeypatch.setattr(executor.Path, "home", lambda: tmp_path)
    token = _make_fake_token(tmp_path)
    token_path = str(token)

    config = {
        "enabled": True,
        "type": "bubblewrap",
        "profile": profile,
        "workspace": str(tmp_path),
        "network": profile != "strict",
    }
    cmd = executor.build_bwrap_args(
        config, ["agy", "--model", "Gemini 3.7 Flash (High)", "--print"]
    )
    triples = [cmd[i : i + 3] for i in range(len(cmd) - 2)]
    assert ["--ro-bind", token_path, token_path] in triples


def test_antigravity_basename_gets_token_ro_bind(tmp_path, monkeypatch):
    """`antigravity` basename is also detected as AGY."""
    monkeypatch.setattr(executor.Path, "home", lambda: tmp_path)
    token = _make_fake_token(tmp_path)
    token_path = str(token)

    config = {
        "enabled": True,
        "type": "bubblewrap",
        "profile": "balanced",
        "workspace": str(tmp_path),
        "network": True,
    }
    cmd = executor.build_bwrap_args(
        config, ["antigravity", "--model", "Gemini 3.7 Flash (High)", "--print"]
    )
    triples = [cmd[i : i + 3] for i in range(len(cmd) - 2)]
    assert ["--ro-bind", token_path, token_path] in triples


@pytest.mark.parametrize(
    "child",
    [
        ["opencode", "run"],
        ["codex", "exec", "--full-auto", "-"],
        ["claude", "--print"],
        ["gemini", "-y", "-p"],
    ],
)
def test_non_agy_children_no_token_bind(child, tmp_path, monkeypatch):
    """Non-AGY children must not receive the token bind."""
    monkeypatch.setattr(executor.Path, "home", lambda: tmp_path)
    _make_fake_token(tmp_path)
    token_path = str(tmp_path / ".gemini" / "antigravity-cli" / "antigravity-oauth-token")

    config = {
        "enabled": True,
        "type": "bubblewrap",
        "profile": "balanced",
        "workspace": str(tmp_path),
        "network": True,
    }
    cmd = executor.build_bwrap_args(config, child)
    joined = " ".join(cmd)
    assert token_path not in joined


@pytest.mark.parametrize(
    "child",
    [
        ["agy", "--model", "Gemini 3.7 Flash (High)", "--print"],
        ["opencode", "run"],
        ["codex", "exec", "--full-auto", "-"],
        ["claude", "--print"],
    ],
)
def test_no_gemini_directory_bind_for_any_cli(child, tmp_path, monkeypatch):
    """No argv entry binds ~/.gemini or ~/.gemini/antigravity-cli as a directory."""
    monkeypatch.setattr(executor.Path, "home", lambda: tmp_path)
    _make_fake_token(tmp_path)
    agy_dir = str(tmp_path / ".gemini" / "antigravity-cli")
    gemini_dir = str(tmp_path / ".gemini")

    config = {
        "enabled": True,
        "type": "bubblewrap",
        "profile": "balanced",
        "workspace": str(tmp_path),
        "network": True,
    }
    cmd = executor.build_bwrap_args(config, child)
    # Walk triples to check --bind / --ro-bind don't target the directories.
    for i in range(len(cmd) - 2):
        if cmd[i] in ("--bind", "--ro-bind"):
            assert cmd[i + 1] != agy_dir, f"directory bind for {agy_dir}"
            assert cmd[i + 2] != agy_dir, f"directory bind target for {agy_dir}"
            assert cmd[i + 1] != gemini_dir, f"directory bind for {gemini_dir}"
            assert cmd[i + 2] != gemini_dir, f"directory bind target for {gemini_dir}"


def test_agy_token_mode_and_bytes_unchanged_after_build(tmp_path, monkeypatch):
    """build_bwrap_args uses the host file in place — no copy, chmod, or rewrite."""
    monkeypatch.setattr(executor.Path, "home", lambda: tmp_path)
    contents = "secret-oauth-token-bytes"
    token = _make_fake_token(tmp_path, contents=contents)

    config = {
        "enabled": True,
        "type": "bubblewrap",
        "profile": "balanced",
        "workspace": str(tmp_path),
        "network": True,
    }
    executor.build_bwrap_args(
        config, ["agy", "--model", "Gemini 3.7 Flash (High)", "--print"]
    )

    assert token.stat().st_mode & 0o777 == 0o600
    assert token.read_text() == contents


def test_agy_missing_token_build_does_not_raise(tmp_path, monkeypatch):
    """build_bwrap_args must not crash when the token file is absent."""
    monkeypatch.setattr(executor.Path, "home", lambda: tmp_path)

    config = {
        "enabled": True,
        "type": "bubblewrap",
        "profile": "balanced",
        "workspace": str(tmp_path),
        "network": True,
    }
    cmd = executor.build_bwrap_args(
        config, ["agy", "--model", "Gemini 3.7 Flash (High)", "--print"]
    )
    token_path = str(tmp_path / ".gemini" / "antigravity-cli" / "antigravity-oauth-token")
    assert token_path not in " ".join(cmd)


def test_agy_symlinked_directory_token_is_rejected(tmp_path, monkeypatch):
    """A token symlink must not turn the single-file bind into a directory bind."""
    monkeypatch.setattr(executor.Path, "home", lambda: tmp_path)
    private_dir = tmp_path / "private-agy-state"
    private_dir.mkdir()
    (private_dir / "conversation_summaries.db").write_text("must-not-leak")
    token = tmp_path / ".gemini" / "antigravity-cli" / "antigravity-oauth-token"
    token.parent.mkdir(parents=True)
    token.symlink_to(private_dir, target_is_directory=True)

    config = {
        "enabled": True,
        "type": "bubblewrap",
        "profile": "balanced",
        "workspace": str(tmp_path),
        "network": True,
    }
    cmd = executor.build_bwrap_args(config, ["agy", "models"])

    assert str(token) not in " ".join(cmd)
    assert str(private_dir) not in " ".join(cmd)


def test_agy_child_no_opencode_writable_binds(tmp_path, monkeypatch):
    """AGY child must not receive opencode_state/cache/config writable binds."""
    monkeypatch.setattr(executor.Path, "home", lambda: tmp_path)
    _make_fake_token(tmp_path)

    config = {
        "enabled": True,
        "type": "bubblewrap",
        "profile": "dev",
        "workspace": str(tmp_path),
        "network": True,
    }
    cmd = executor.build_bwrap_args(
        config, ["agy", "--model", "Gemini 3.7 Flash (High)", "--print"]
    )
    joined = " ".join(cmd)
    assert ".local/share/opencode" not in joined
    assert ".cache/opencode" not in joined
    assert ".config/opencode" not in joined


def test_agy_tmpfs_before_ro_bind_ordering(tmp_path, monkeypatch):
    """--tmpfs for the parent dir must come before --ro-bind of the token."""
    monkeypatch.setattr(executor.Path, "home", lambda: tmp_path)
    token = _make_fake_token(tmp_path)
    parent = str(token.parent)
    token_path = str(token)

    config = {
        "enabled": True,
        "type": "bubblewrap",
        "profile": "balanced",
        "workspace": str(tmp_path),
        "network": True,
    }
    cmd = executor.build_bwrap_args(
        config, ["agy", "--model", "Gemini 3.7 Flash (High)", "--print"]
    )
    tmpfs_idx = cmd.index("--tmpfs")
    tmpfs_path_idx = cmd.index(parent, tmpfs_idx)
    ro_bind_idx = cmd.index("--ro-bind", tmpfs_path_idx)
    token_idx = cmd.index(token_path, ro_bind_idx)
    assert tmpfs_idx < tmpfs_path_idx < ro_bind_idx < token_idx


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


def test_sandbox_preflight_network_modes_have_distinct_cache_entries(preflight_env, monkeypatch):
    calls = []

    def fake_run(*a, **kw):
        calls.append(a)
        return _ProbeResult(0)

    monkeypatch.setattr(executor.subprocess, "run", fake_run)
    executor.sandbox_preflight(**preflight_env)
    executor.sandbox_preflight(
        preflight_env["cli_info"],
        {**preflight_env["sandbox_config"], "network": False},
        preflight_env["cwd"],
    )

    assert len(calls) == 2


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


# ---------------------------------------------------------------------------
# AGY preflight tests
# ---------------------------------------------------------------------------

@pytest.fixture()
def agy_preflight_env(tmp_path, monkeypatch):
    """Fixture for AGY preflight tests with a fake token file."""
    executor._SANDBOX_PREFLIGHT_CACHE.clear()
    monkeypatch.setattr(executor.Path, "home", lambda: tmp_path)
    _make_fake_token(tmp_path)
    yield {
        "cli_info": {
            "command": ["agy", "--model", "Gemini 3.7 Flash (High)", "--print"],
            "env": {},
        },
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


def test_agy_preflight_success(agy_preflight_env, monkeypatch):
    """AGY preflight returns None when agy models exits 0."""
    calls = []

    def fake_run(cmd, **kw):
        calls.append(cmd)
        # First call: --version probe (exit 0).
        # Second call: agy models (exit 0).
        return _ProbeResult(0, stdout="gemini-3.7-flash")

    monkeypatch.setattr(executor.subprocess, "run", fake_run)
    assert executor.sandbox_preflight(**agy_preflight_env) is None
    # Two subprocess calls: version probe + agy models
    assert len(calls) == 2


def test_agy_preflight_nonzero_exit(agy_preflight_env, monkeypatch):
    """AGY preflight returns error when agy models exits non-zero."""
    call_count = [0]

    def fake_run(cmd, **kw):
        call_count[0] += 1
        if call_count[0] == 1:
            return _ProbeResult(0, stdout="1.1.17")
        return _ProbeResult(1, stderr="Please log in to continue")

    monkeypatch.setattr(executor.subprocess, "run", fake_run)
    error = executor.sandbox_preflight(**agy_preflight_env)
    assert error is not None
    assert "AGY auth preflight" in error
    assert "antigravity-oauth-token" in error
    assert "agy" in error.lower() or "log in" in error.lower()


def test_agy_preflight_timeout(agy_preflight_env, monkeypatch):
    """AGY preflight returns error on timeout, naming AGY_AUTH_PREFLIGHT_TIMEOUT."""
    call_count = [0]

    def fake_run(cmd, **kw):
        call_count[0] += 1
        if call_count[0] == 1:
            return _ProbeResult(0, stdout="1.1.17")
        raise subprocess.TimeoutExpired(cmd=cmd, timeout=executor.AGY_AUTH_PREFLIGHT_TIMEOUT)

    monkeypatch.setattr(executor.subprocess, "run", fake_run)
    error = executor.sandbox_preflight(**agy_preflight_env)
    assert error is not None
    assert "timed out" in error
    assert str(executor.AGY_AUTH_PREFLIGHT_TIMEOUT) in error


def test_agy_preflight_caches_per_shape(agy_preflight_env, monkeypatch):
    """Second preflight call with the same shape does not re-invoke subprocess."""
    calls = []

    def fake_run(cmd, **kw):
        calls.append(cmd)
        return _ProbeResult(0, stdout="ok")

    monkeypatch.setattr(executor.subprocess, "run", fake_run)
    executor.sandbox_preflight(**agy_preflight_env)
    executor.sandbox_preflight(**agy_preflight_env)
    assert len(calls) == 2  # version + agy models, only once


def test_agy_preflight_missing_token(tmp_path, monkeypatch):
    """Preflight returns actionable error when the token file is missing."""
    executor._SANDBOX_PREFLIGHT_CACHE.clear()
    monkeypatch.setattr(executor.Path, "home", lambda: tmp_path)
    # No token file created.

    def boom(*a, **kw):
        raise AssertionError("subprocess must not run when token is missing")

    monkeypatch.setattr(executor.subprocess, "run", boom)

    env = {
        "cli_info": {"command": ["agy", "--print"], "env": {}},
        "sandbox_config": {
            "enabled": True,
            "type": "bubblewrap",
            "profile": "balanced",
            "workspace": str(tmp_path),
            "network": True,
        },
        "cwd": str(tmp_path),
    }
    # Version probe still runs (subprocess is mocked to boom), but we need
    # the version probe to pass first.  Let's allow the first call.
    call_count = [0]

    def fake_run(cmd, **kw):
        call_count[0] += 1
        if call_count[0] == 1:
            return _ProbeResult(0, stdout="1.1.17")
        raise AssertionError("agy models must not run when token is missing")

    monkeypatch.setattr(executor.subprocess, "run", fake_run)
    error = executor.sandbox_preflight(**env)
    assert error is not None
    assert "antigravity-oauth-token" in error
    executor._SANDBOX_PREFLIGHT_CACHE.clear()


def test_agy_preflight_not_invoked_for_non_agy(tmp_path, monkeypatch):
    """AGY preflight must not run for non-AGY commands."""
    executor._SANDBOX_PREFLIGHT_CACHE.clear()
    monkeypatch.setattr(executor.Path, "home", lambda: tmp_path)

    calls = []

    def fake_run(cmd, **kw):
        calls.append(cmd)
        # Inspect the child command in the bwrap argv (after --)
        sep_idx = cmd.index("--")
        child = cmd[sep_idx + 1:]
        if child[0] == "agy":
            raise AssertionError("agy preflight must not run for non-agy command")
        return _ProbeResult(0, stdout="1.2.3")

    monkeypatch.setattr(executor.subprocess, "run", fake_run)

    env = {
        "cli_info": {"command": ["codex", "exec", "--full-auto"], "env": {}},
        "sandbox_config": {
            "enabled": True,
            "type": "bubblewrap",
            "profile": "balanced",
            "workspace": str(tmp_path),
            "network": True,
        },
        "cwd": str(tmp_path),
    }
    assert executor.sandbox_preflight(**env) is None
    # Only the version probe should run (1 call)
    assert len(calls) == 1
    executor._SANDBOX_PREFLIGHT_CACHE.clear()


def test_claude_preflight_still_runs_for_claude(tmp_path, monkeypatch):
    """Claude auth preflight must still run for claude commands (unchanged)."""
    executor._SANDBOX_PREFLIGHT_CACHE.clear()
    monkeypatch.setattr(executor.Path, "home", lambda: tmp_path)

    # Create Claude credential files so the bind works.
    claude_dir = tmp_path / ".claude"
    claude_dir.mkdir(parents=True, exist_ok=True)
    (claude_dir / ".credentials.json").write_text('{"loggedIn": true}')
    (tmp_path / ".claude.json").write_text("{}")

    calls = []

    def fake_run(cmd, **kw):
        calls.append(cmd)
        sep_idx = cmd.index("--")
        child = cmd[sep_idx + 1:]
        if child[0] == "claude" and len(child) > 1 and child[1] == "auth":
            return _ProbeResult(0, stdout='{"loggedIn": true}')
        return _ProbeResult(0, stdout="1.0.0")

    monkeypatch.setattr(executor.subprocess, "run", fake_run)

    env = {
        "cli_info": {"command": ["claude", "--print"], "env": {}},
        "sandbox_config": {
            "enabled": True,
            "type": "bubblewrap",
            "profile": "balanced",
            "workspace": str(tmp_path),
            "network": True,
        },
        "cwd": str(tmp_path),
    }
    assert executor.sandbox_preflight(**env) is None
    # Two calls: version probe + claude auth status
    assert len(calls) == 2
    executor._SANDBOX_PREFLIGHT_CACHE.clear()


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
