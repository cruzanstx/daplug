"""Pin the executor facade surface so future module splits can't silently drop a re-export.

Every name listed here is referenced by at least one test file via ``executor.<name>``
or ``monkeypatch.setattr(executor, "<name>", ...)``.  After the split into focused
sub-modules (paths, repostate, worktree, models, sandbox, loop), executor.py re-exports
all of them.  This test ensures they remain accessible.
"""
import sys
from pathlib import Path

import pytest

SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.append(str(SCRIPT_DIR))

import executor  # noqa: E402


# Every name that tests historically access on the executor module.
# Grouped by source module for documentation, but the assertion is one flat list.
FACADE_NAMES = [
    # stdlib module references (patched via executor.subprocess.Popen etc.)
    "subprocess",
    "shutil",
    "Path",
    # paths.py
    "get_repo_root",
    "_read_config_value",
    "get_cli_logs_dir",
    "get_worktree_dir",
    "detect_default_branch",
    # repostate.py
    "repo_state_snapshot",
    "repo_state_delta",
    "repo_state_delta_paths",
    "_has_real_file_changes",
    "_detect_stalled",
    "_detect_impossible_gate",
    # worktree.py
    "create_worktree",
    "install_worktree_dependencies",
    "normalize_worktree_path",
    "ensure_worktree_permissions",
    # models.py
    "get_cli_info",
    "MODEL_SPECS",
    "MODEL_CHOICES",
    "MODEL_REGISTRY_BY_NAME",
    "LEGACY_MODEL_DISPLAY",
    "_resolve_router_command",
    "_require_claude_cli",
    "_load_model_registry",
    "_REQUIRED_MODEL_FIELDS",
    "_ALLOWED_STDIN_MODES",
    "CLI_OVERRIDE_SUPPORTED_MODELS",
    # sandbox.py
    "resolve_sandbox_config",
    "build_bwrap_args",
    "sandbox_preflight",
    "check_bwrap_available",
    "maybe_wrap_command_with_sandbox",
    "raise_on_execution_error",
    "SANDBOX_ENV_PASSTHROUGH",
    "_SANDBOX_PREFLIGHT_CACHE",
    "_sandbox_passthrough_env",
    "BWRAP_PROFILES",
    "BWRAP_MISSING_ERROR",
    # loop.py
    "get_loop_state_dir",
    "run_cli",
    "run_cli_foreground",
    "run_verification_loop",
    "run_verification_loop_background",
    "wrap_prompt_with_verification_protocol",
    "check_completion_marker",
    "DEFAULT_COMPLETION_MARKER",
    "INSTRUCTIONS_END_SENTINEL",
    # executor.py (stays here)
    "main",
    "extract_prompt_title",
    "expand_prompt_input",
    "resolve_prompt",
    "resolve_prompts",
]


@pytest.mark.parametrize("name", FACADE_NAMES)
def test_executor_facade_reexports_name(name):
    """Each historically-accessed name must resolve on the executor module."""
    assert hasattr(executor, name), (
        f"executor.{name} is missing — the facade re-export was dropped. "
        f"Add it to the import block in executor.py."
    )


def test_facade_name_count():
    """Guard against accidental shrinkage of the facade surface."""
    assert len(FACADE_NAMES) >= 50, (
        f"Facade surface has only {len(FACADE_NAMES)} names — expected at least 50. "
        f"Did a name get removed without updating this test?"
    )
