#!/usr/bin/env python3
"""Path and configuration helpers for the prompt executor."""

import os
import subprocess
import sys
from pathlib import Path
from typing import Optional

def get_repo_root() -> Path:
    """Get git repository root."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, check=True
        )
        return Path(result.stdout.strip())
    except (subprocess.CalledProcessError, FileNotFoundError, OSError):
        return Path.cwd()


def _read_config_value(repo_root: Path, key: str) -> Optional[str]:
    """Read a config value via config-reader if available."""
    config_reader = Path(__file__).resolve().parents[3] / "skills" / "config-reader" / "scripts" / "config.py"
    if not config_reader.exists():
        return None
    try:
        result = subprocess.run(
            [sys.executable, str(config_reader), "get", key, "--repo-root", str(repo_root), "--quiet"],
            capture_output=True,
            text=True,
            check=False,
        )
        value = result.stdout.strip()
        return value if value else None
    except OSError:
        return None


def get_cli_logs_dir(repo_root: Path) -> Path:
    configured = _read_config_value(repo_root, "cli_logs_dir")
    if configured:
        expanded = os.path.expandvars(os.path.expanduser(configured))
        log_path = Path(expanded)
        if not log_path.is_absolute():
            return (repo_root / log_path).resolve()
        return log_path
    return Path.home() / ".claude" / "cli-logs"


def get_worktree_dir(repo_root: Path) -> Path:
    """Get worktree directory from <daplug_config> or use default.

    Priority: project CLAUDE.md -> global ~/.claude/CLAUDE.md -> .worktrees/
    """
    configured = _read_config_value(repo_root, "worktree_dir")
    if configured:
        if configured.startswith('.') or not configured.startswith('/'):
            return (repo_root / configured).resolve()
        return Path(configured)

    # Default: .worktrees/ inside repo
    return (repo_root / ".worktrees").resolve()


def detect_default_branch(repo_root: Path) -> str:
    """Detect the repo's default branch.

    Priority: origin/HEAD symbolic ref -> currently checked-out branch -> "main".
    """
    r = subprocess.run(
        ["git", "symbolic-ref", "--short", "refs/remotes/origin/HEAD"],
        capture_output=True, text=True, cwd=repo_root,
    )
    if r.returncode == 0 and r.stdout.strip():
        ref = r.stdout.strip()
        return ref.split("/", 1)[1] if "/" in ref else ref
    r = subprocess.run(
        ["git", "branch", "--show-current"],
        capture_output=True, text=True, cwd=repo_root,
    )
    if r.returncode == 0 and r.stdout.strip():
        return r.stdout.strip()
    return "main"
