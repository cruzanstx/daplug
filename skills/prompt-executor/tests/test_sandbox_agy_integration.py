"""Integration test: real bwrap + agy inside a sandbox on this host.

Skipped automatically when ``bwrap``, ``agy``, or the host OAuth token is
missing.  When all three are present, verifies that:

1. ``agy models`` exits 0 inside a balanced-profile bwrap sandbox.
2. ``ls ~/.gemini/antigravity-cli`` inside the sandbox shows only the token
   file (no ``conversations``, no ``*.db``).
3. The host token file is unchanged (mode 0600, same bytes) after the run.

Never prints or logs token contents.
"""
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.append(str(SCRIPT_DIR))

import executor  # noqa: E402
import sandbox  # noqa: E402

_TOKEN_PATH = Path.home() / ".gemini" / "antigravity-cli" / "antigravity-oauth-token"


def _has_bwrap() -> bool:
    return shutil.which("bwrap") is not None


def _has_agy() -> bool:
    return shutil.which("agy") is not None or shutil.which("antigravity") is not None


def _has_token() -> bool:
    return _TOKEN_PATH.exists()


pytestmark = pytest.mark.integration

skip_reason = (
    "Requires bwrap, agy, and ~/.gemini/antigravity-cli/antigravity-oauth-token"
)


@pytest.mark.skipif(
    not (_has_bwrap() and _has_agy() and _has_token()),
    reason=skip_reason,
)
def test_agy_models_in_sandbox(tmp_path):
    """Run ``agy models`` inside a balanced-profile bwrap sandbox and verify exit 0."""
    config = {
        "enabled": True,
        "type": "bubblewrap",
        "profile": "balanced",
        "workspace": str(tmp_path),
        "network": True,
    }
    cmd = sandbox.build_bwrap_args(config, ["agy", "models"])
    proc = subprocess.run(
        cmd,
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert proc.returncode == 0, f"agy models failed:\n{proc.stderr}"
    assert proc.stdout.strip(), "agy models produced no output"


@pytest.mark.skipif(
    not (_has_bwrap() and _has_agy() and _has_token()),
    reason=skip_reason,
)
def test_agy_sandbox_only_token_visible(tmp_path):
    """``ls ~/.gemini/antigravity-cli`` inside the sandbox shows only the token file."""
    config = {
        "enabled": True,
        "type": "bubblewrap",
        "profile": "balanced",
        "workspace": str(tmp_path),
        "network": True,
    }
    agy_dir = str(Path.home() / ".gemini" / "antigravity-cli")
    # Build for an AGY child so CLI-specific auth binds are included, then
    # replace only the child command to inspect that exact sandbox shape.
    cmd = sandbox.build_bwrap_args(config, ["agy", "models"])
    separator = cmd.index("--")
    cmd = [*cmd[: separator + 1], "ls", "-1", agy_dir]
    proc = subprocess.run(
        cmd,
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert proc.returncode == 0, f"ls failed:\n{proc.stderr}"
    entries = [e for e in proc.stdout.strip().splitlines() if e]
    assert entries == ["antigravity-oauth-token"]


@pytest.mark.skipif(
    not (_has_bwrap() and _has_agy() and _has_token()),
    reason=skip_reason,
)
def test_agy_sandbox_token_unchanged(tmp_path):
    """Host token file mode and bytes are unchanged after sandbox execution."""
    original_mode = _TOKEN_PATH.stat().st_mode & 0o777
    original_bytes = _TOKEN_PATH.read_bytes()

    config = {
        "enabled": True,
        "type": "bubblewrap",
        "profile": "balanced",
        "workspace": str(tmp_path),
        "network": True,
    }
    cmd = sandbox.build_bwrap_args(config, ["agy", "models"])
    subprocess.run(
        cmd,
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
        timeout=120,
    )

    assert _TOKEN_PATH.stat().st_mode & 0o777 == original_mode
    assert _TOKEN_PATH.read_bytes() == original_bytes
