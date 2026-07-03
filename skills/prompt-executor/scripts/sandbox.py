#!/usr/bin/env python3
"""Bubblewrap sandbox configuration, argument building, and preflight checks."""

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Optional

BWRAP_PROFILES = {
    "strict": {
        "network": False,
        "writable": ["workspace", "opencode_state"],
        "minimal_env": True,
    },
    "balanced": {
        "network": True,
        "writable": ["workspace", "opencode_state", "opencode_cache", "opencode_config"],
        "minimal_env": True,
    },
    "dev": {
        "network": True,
        "writable": ["workspace", "opencode_state", "opencode_cache", "opencode_config", "tool_caches"],
        "minimal_env": False,
    },
}

# Credential env vars that must survive bwrap --clearenv. These providers
# authenticate from the environment (not from a bind-mounted auth store), so
# stripping them breaks every request while --share-net is active anyway.
SANDBOX_ENV_PASSTHROUGH = ("SYNTHETIC_API_KEY", "LMSTUDIO_API_KEY")

BWRAP_MISSING_ERROR = (
    "Error: bubblewrap (bwrap) not found in PATH.\n\n"
    "Install with:\n"
    "  apt:   sudo apt install bubblewrap\n"
    "  dnf:   sudo dnf install bubblewrap\n"
    "  pacman: sudo pacman -S bubblewrap\n\n"
    "To run without sandbox: add --no-sandbox"
)

def get_sandbox_add_dirs(cwd: Optional[str] = None) -> list[str]:
    """Get additional directories that should be writable for codex sandbox.

    These are needed because codex's workspace-write sandbox only allows writes
    to the workspace directory, but git operations and Go builds need access to:
    - ~/.cache/go-build (Go build cache)
    - ~/go/pkg/mod (Go module cache)
    - Git worktree .git directories (outside workspace, in main repo)
    - npm cache
    """
    home = Path.home()
    add_dirs = []

    # Go caches - needed for go build/test
    go_cache = home / ".cache" / "go-build"
    if go_cache.exists() or (home / ".cache").exists():
        add_dirs.extend(["--add-dir", str(home / ".cache")])

    go_mod = home / "go" / "pkg"
    if go_mod.exists() or (home / "go").exists():
        add_dirs.extend(["--add-dir", str(home / "go")])

    # npm/node caches - needed for npm install
    npm_cache = home / ".npm"
    if npm_cache.exists():
        add_dirs.extend(["--add-dir", str(npm_cache)])

    # Git worktree support - if cwd is a worktree, add the main repo's .git dir
    # Worktrees have a .git file (not directory) pointing to the main repo
    if cwd:
        git_file = Path(cwd) / ".git"
        if git_file.exists() and git_file.is_file():
            try:
                content = git_file.read_text().strip()
                # Format: "gitdir: /path/to/main/repo/.git/worktrees/name"
                if content.startswith("gitdir:"):
                    gitdir = content.split(":", 1)[1].strip()
                    # Go up from .git/worktrees/name to .git
                    main_git = Path(gitdir).parent.parent
                    if main_git.exists() and main_git.name == ".git":
                        add_dirs.extend(["--add-dir", str(main_git)])
            except Exception:
                pass  # Ignore errors reading .git file

    return add_dirs


def resolve_sandbox_config(platform: str, args: argparse.Namespace, cwd: str) -> dict:
    if getattr(args, "sandbox", False) and getattr(args, "no_sandbox", False):
        raise ValueError("Cannot pass both --sandbox and --no-sandbox")

    sandbox_type = getattr(args, "sandbox_type", None)
    sandbox_enabled_flag = bool(getattr(args, "sandbox", False))
    sandbox_disabled_flag = bool(getattr(args, "no_sandbox", False))

    if sandbox_type and (sandbox_disabled_flag or not sandbox_enabled_flag):
        raise ValueError("--sandbox-type requires sandboxing to be enabled (use --sandbox)")

    profile = getattr(args, "sandbox_profile", "balanced") or "balanced"
    if profile not in BWRAP_PROFILES:
        raise ValueError(f"Invalid --sandbox-profile: {profile}")

    workspace_input = getattr(args, "sandbox_workspace", None) or cwd
    workspace = str(Path(workspace_input).expanduser().resolve())

    if sandbox_disabled_flag or not sandbox_enabled_flag:
        enabled = False
        resolved_type = None
    else:
        resolved_type = sandbox_type
        is_linux = platform.startswith("linux")
        if resolved_type is None:
            if is_linux:
                resolved_type = "bubblewrap"
                enabled = True
            else:
                print(
                    "[Sandbox] Warning: --sandbox requested on non-Linux without --sandbox-type; sandbox disabled.",
                    file=sys.stderr,
                )
                enabled = False
        else:
            if resolved_type == "bubblewrap" and not is_linux:
                raise ValueError("--sandbox-type bubblewrap is only supported on Linux")
            enabled = True

    network_flag = getattr(args, "sandbox_net", None)
    if network_flag is None:
        network = bool(BWRAP_PROFILES[profile]["network"])
    elif network_flag == "on":
        network = True
    elif network_flag == "off":
        network = False
    else:
        raise ValueError(f"Invalid --sandbox-net value: {network_flag}")

    return {
        "enabled": enabled,
        "type": resolved_type,
        "profile": profile,
        "workspace": workspace,
        "network": network,
    }


def check_bwrap_available() -> bool:
    return shutil.which("bwrap") is not None


def _existing_paths(paths: list[str]) -> list[str]:
    return [p for p in paths if Path(p).exists()]


def _path_within(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def _node_version_root(path: Path, home: Path) -> Optional[Path]:
    node_versions = home / ".nvm" / "versions" / "node"
    try:
        rel = path.relative_to(node_versions)
    except ValueError:
        return None
    if not rel.parts:
        return None
    return node_versions / rel.parts[0]


def _selected_cli_runtime_paths(child_command: list[str], home: Path) -> list[str]:
    """Return read-only bind roots needed to execute the selected CLI.

    nvm/bun-installed CLIs are commonly exposed through symlinks in PATH. Binding
    only system paths leaves those symlinks broken inside bwrap, so bind the
    command's PATH directory and the resolved package-manager runtime root.
    """
    if not child_command:
        return []

    executable = child_command[0]
    executable_path = Path(executable)
    if executable_path.is_absolute() or executable_path.parent != Path("."):
        found = executable_path
    else:
        resolved = shutil.which(executable)
        if not resolved:
            return []
        found = Path(resolved)

    paths: list[Path] = []
    if found.exists():
        paths.append(found.parent)
        resolved_found = found.resolve()
        node_root = _node_version_root(resolved_found, home)
        if node_root:
            paths.append(node_root)

        bun_global = home / ".bun" / "install" / "global"
        if _path_within(resolved_found, bun_global):
            paths.extend([home / ".bun" / "bin", bun_global])

        volta_root = home / ".volta"
        if _path_within(resolved_found, volta_root):
            paths.append(volta_root)

    seen: set[str] = set()
    result: list[str] = []
    for path in paths:
        if not path.exists():
            continue
        item = str(path)
        if item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result


def _sandbox_passthrough_env(cli_info: dict) -> dict[str, str]:
    """Env-keyed credentials to re-inject after bwrap --clearenv."""
    extra = {k: v for k, v in cli_info.get("env", {}).items() if v}
    for key in SANDBOX_ENV_PASSTHROUGH:
        value = os.environ.get(key)
        if value and key not in extra:
            extra[key] = value
    return extra


def build_bwrap_args(
    config: dict,
    child_command: list[str],
    extra_env: Optional[dict[str, str]] = None,
) -> list[str]:
    workspace = config["workspace"]
    profile = config["profile"]
    profile_cfg = BWRAP_PROFILES[profile]
    home = str(Path.home())

    if not Path(workspace).exists():
        raise ValueError(f"Sandbox workspace does not exist: {workspace}")

    cmd = [
        "bwrap",
        "--unshare-all",
        "--new-session",
        "--die-with-parent",
        "--dev",
        "/dev",
        "--proc",
        "/proc",
        "--tmpfs",
        "/tmp",
        "--tmpfs",
        "/run",
    ]

    if config["network"]:
        cmd.append("--share-net")

    if profile_cfg.get("minimal_env"):
        cmd.extend([
            "--clearenv",
            "--setenv",
            "PATH",
            os.environ.get("PATH", "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"),
            "--setenv",
            "HOME",
            home,
            "--setenv",
            "USER",
            os.environ.get("USER", "user"),
            "--setenv",
            "LANG",
            os.environ.get("LANG", "C.UTF-8"),
            "--setenv",
            "TERM",
            os.environ.get("TERM", "xterm-256color"),
        ])
        for key, value in (extra_env or {}).items():
            cmd.extend(["--setenv", key, value])

    readonly_paths = _existing_paths([
        "/usr",
        "/bin",
        "/lib",
        "/lib64",
        "/usr/lib",
        "/usr/lib64",
        "/etc/resolv.conf",
        "/etc/hosts",
        "/etc/ssl",
    ])
    for path in readonly_paths:
        cmd.extend(["--ro-bind", path, path])

    writable_paths = {
        "workspace": [workspace],
        "opencode_state": [str(Path(home) / ".local" / "share" / "opencode")],
        "opencode_cache": [str(Path(home) / ".cache" / "opencode")],
        "opencode_config": [str(Path(home) / ".config" / "opencode")],
        "tool_caches": [
            str(Path(home) / ".cache" / "go-build"),
            str(Path(home) / "go" / "pkg" / "mod"),
            str(Path(home) / ".npm"),
        ],
    }

    for key in profile_cfg["writable"]:
        for path in writable_paths.get(key, []):
            p = Path(path)
            if key == "workspace":
                cmd.extend(["--bind", str(p), str(p)])
                continue
            p.mkdir(parents=True, exist_ok=True)
            cmd.extend(["--bind", str(p), str(p)])

    for path in _selected_cli_runtime_paths(child_command, Path(home)):
        cmd.extend(["--ro-bind", path, path])

    cmd.extend(["--", *child_command])
    return cmd


SANDBOX_PREFLIGHT_TIMEOUT = 60

# Keyed by (binary, profile, workspace); a loop re-probes only when the
# sandbox shape changes, not on every iteration.
_SANDBOX_PREFLIGHT_CACHE: dict[tuple, Optional[str]] = {}


def sandbox_preflight(cli_info: dict, sandbox_config: Optional[dict], cwd: str) -> Optional[str]:
    """Probe the CLI inside the sandbox before real execution.

    Runs `<binary> --version` under the same bwrap invocation the real run
    will use, so environmental breakage (missing runtime binds, crashed
    startup, stripped credentials for the probe's own launch) surfaces as an
    immediate, diagnosable error instead of burning loop iterations.
    Returns an error message on failure, None when the probe passes.
    """
    if not sandbox_config or not sandbox_config.get("enabled"):
        return None
    if sandbox_config.get("type") != "bubblewrap":
        return None
    command = cli_info.get("command") or []
    if not command:
        return None

    binary = command[0]
    cache_key = (binary, sandbox_config.get("profile"), sandbox_config.get("workspace"))
    if cache_key in _SANDBOX_PREFLIGHT_CACHE:
        return _SANDBOX_PREFLIGHT_CACHE[cache_key]

    probe_cmd = build_bwrap_args(
        sandbox_config,
        [binary, "--version"],
        extra_env=_sandbox_passthrough_env(cli_info),
    )
    error: Optional[str] = None
    try:
        proc = subprocess.run(
            probe_cmd,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=SANDBOX_PREFLIGHT_TIMEOUT,
        )
        if proc.returncode != 0:
            output_lines = ((proc.stdout or "") + (proc.stderr or "")).strip().splitlines()
            tail = output_lines[-1] if output_lines else "(no output)"
            error = _sandbox_error_message(
                sandbox_config,
                f"preflight probe '{binary} --version' failed inside the sandbox "
                f"(exit {proc.returncode}): {tail}",
            )
    except subprocess.TimeoutExpired:
        error = _sandbox_error_message(
            sandbox_config,
            f"preflight probe '{binary} --version' timed out after "
            f"{SANDBOX_PREFLIGHT_TIMEOUT}s inside the sandbox",
        )
    except OSError as exc:
        error = _sandbox_error_message(sandbox_config, f"preflight probe could not launch: {exc}")

    _SANDBOX_PREFLIGHT_CACHE[cache_key] = error
    return error


def _sandbox_config_summary(config: Optional[dict]) -> str:
    if not config:
        return "type=none, profile=balanced, workspace=n/a, network=off"
    network = "on" if config.get("network") else "off"
    return (
        f"type={config.get('type') or 'none'}, "
        f"profile={config.get('profile', 'balanced')}, "
        f"workspace={config.get('workspace', 'n/a')}, "
        f"network={network}"
    )


def _sandbox_error_message(config: dict, reason: str) -> str:
    summary = _sandbox_config_summary(config)
    return (
        f"Sandbox launch failed: {reason}\n"
        f"Sandbox config: {summary}\n"
        "Hints: verify bwrap is installed and the workspace/bind paths exist, or run with --no-sandbox."
    )


def raise_on_execution_error(execution: dict, sandbox_config: Optional[dict] = None) -> None:
    if execution.get("status") != "error":
        return
    message = execution.get("error") or "Execution failed"
    if sandbox_config and sandbox_config.get("enabled") and "Sandbox config:" not in message:
        message = _sandbox_error_message(sandbox_config, message)
    raise RuntimeError(message)


def maybe_wrap_command_with_sandbox(
    command: Optional[list[str]],
    sandbox_config: Optional[dict],
    extra_env: Optional[dict[str, str]] = None,
) -> list[str]:
    # extra_env carries credentials; omit it on preview/info paths so secrets
    # never appear in printed commands or logs.
    if command is None:
        return []
    if not sandbox_config or not sandbox_config.get("enabled"):
        return command
    if sandbox_config.get("type") == "bubblewrap":
        return build_bwrap_args(sandbox_config, command, extra_env=extra_env)
    return command
