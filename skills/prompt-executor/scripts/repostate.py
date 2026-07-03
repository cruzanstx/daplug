#!/usr/bin/env python3
"""Repository-state snapshot, diff, and stalled-loop detection."""

import re
import subprocess
import time
from pathlib import Path
from typing import Optional

def _empty_repo_state_snapshot() -> dict:
    return {"modified": {}, "untracked": set()}


def _snapshot_timeout(deadline: float) -> float:
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise subprocess.TimeoutExpired("repo_state_snapshot", 30)
    return remaining


def _run_snapshot_git(repo_root: str, args: list[str], deadline: float, *, text: bool):
    return subprocess.run(
        ["git", "-C", repo_root, *args],
        capture_output=True,
        text=text,
        timeout=_snapshot_timeout(deadline),
    )


def _split_nul_paths(raw: bytes) -> list[str]:
    return [
        path
        for path in raw.decode("utf-8", "surrogateescape").split("\0")
        if path
    ]


def repo_state_snapshot(repo_root: str) -> dict:
    """Return content-aware dirty state for repo_root, or empty state on failure."""
    try:
        deadline = time.monotonic() + 30
        _run_snapshot_git(repo_root, ["update-index", "-q", "--refresh"], deadline, text=True)

        listed_result = _run_snapshot_git(
            repo_root,
            ["ls-files", "-m", "-o", "--exclude-standard", "-z"],
            deadline,
            text=False,
        )
        if listed_result.returncode != 0:
            return _empty_repo_state_snapshot()

        untracked_result = _run_snapshot_git(
            repo_root,
            ["ls-files", "-o", "--exclude-standard", "-z"],
            deadline,
            text=False,
        )
        if untracked_result.returncode != 0:
            return _empty_repo_state_snapshot()

        listed_paths = _split_nul_paths(listed_result.stdout)
        untracked = set(_split_nul_paths(untracked_result.stdout))
        modified = {}
        repo_path = Path(repo_root)

        for path in listed_paths:
            if path in untracked:
                continue
            if not (repo_path / path).exists():
                modified[path] = "<deleted>"
                continue
            hash_result = _run_snapshot_git(
                repo_root,
                ["hash-object", "--", path],
                deadline,
                text=True,
            )
            if hash_result.returncode != 0:
                return _empty_repo_state_snapshot()
            content_hash = hash_result.stdout.strip()
            if not content_hash:
                return _empty_repo_state_snapshot()
            modified[path] = content_hash

        return {"modified": modified, "untracked": untracked}
    except (subprocess.SubprocessError, OSError):
        return _empty_repo_state_snapshot()


def repo_state_delta(before: dict, after: dict) -> dict:
    before_modified = before.get("modified", {})
    after_modified = after.get("modified", {})
    modified_paths = sorted(
        path
        for path in set(before_modified) | set(after_modified)
        if before_modified.get(path) != after_modified.get(path)
    )

    before_untracked = set(before.get("untracked", set()))
    after_untracked = set(after.get("untracked", set()))
    return {
        "modified": modified_paths,
        "new_untracked": sorted(after_untracked - before_untracked),
        "removed_untracked": sorted(before_untracked - after_untracked),
    }


def repo_state_delta_paths(delta: dict) -> list[str]:
    paths = set(delta.get("modified", []))
    paths.update(delta.get("new_untracked", []))
    paths.update(delta.get("removed_untracked", []))
    return sorted(paths)


# ------------------------------------------------------------------
# Loop verification helpers (--require-diff and dead-loop detection)
# ------------------------------------------------------------------

# Executor-injected artifacts that should NOT count as "real" file changes
# when --require-diff is active.
_EXECUTOR_ARTIFACT_PATHS = {"TASK.md"}
_EXECUTOR_ARTIFACT_PREFIXES = (".sisyphus/",)


def _is_executor_artifact(path: str) -> bool:
    """Return True for files injected by the executor itself (not by the agent)."""
    if path in _EXECUTOR_ARTIFACT_PATHS:
        return True
    return any(path.startswith(prefix) for prefix in _EXECUTOR_ARTIFACT_PREFIXES)


def _get_git_head(repo_root: str) -> Optional[str]:
    """Get the current HEAD commit hash, or None if not a git repo."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_root, capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except (subprocess.SubprocessError, OSError):
        pass
    return None


def _snapshot_to_jsonable(snapshot: dict) -> dict:
    """Convert repo_state_snapshot to JSON-serializable form for state persistence."""
    return {
        "modified": dict(snapshot.get("modified", {})),
        "untracked": sorted(snapshot.get("untracked", set())),
    }


def _snapshot_from_jsonable(data: Optional[dict]) -> dict:
    """Convert JSON-serializable snapshot back to repo_state_snapshot form."""
    if not data:
        return _empty_repo_state_snapshot()
    return {
        "modified": dict(data.get("modified", {})),
        "untracked": set(data.get("untracked", [])),
    }


def _has_real_file_changes(
    before_snapshot: dict,
    after_snapshot: dict,
    before_head: Optional[str],
    after_head: Optional[str],
) -> bool:
    """Check if the execution cwd has real file changes, excluding executor artifacts.

    Detects:
    - Uncommitted tracked modifications (via snapshot delta)
    - New or removed untracked files (via snapshot delta)
    - Commits made since the loop started (via HEAD ref comparison)
    """
    delta = repo_state_delta(before_snapshot, after_snapshot)
    changed_paths = repo_state_delta_paths(delta)

    filtered = [p for p in changed_paths if not _is_executor_artifact(p)]
    if filtered:
        return True

    # Agent may have committed its work, leaving the tree clean.
    if before_head and after_head and before_head != after_head:
        return True

    return False


def _normalize_retry_reason(reason: str) -> str:
    """Normalize retry reason for case/whitespace-insensitive comparison."""
    return " ".join(reason.lower().split())


def _detect_stalled(history: list) -> bool:
    """Return True if the last two iterations share the same normalized retry_reason."""
    if len(history) < 2:
        return False
    current = history[-1].get("retry_reason")
    previous = history[-2].get("retry_reason")
    if not current or not previous:
        return False
    return _normalize_retry_reason(current) == _normalize_retry_reason(previous)


# Impossible-gate patterns: retry reasons that no amount of retrying can fix.
_IMPOSSIBLE_GATE_PHRASES = (
    "outside the isolated worktree",
    "isolation boundary",
)


def _detect_impossible_gate(retry_reason: str, execution_cwd: str) -> bool:
    """Return True if a retry_reason indicates an impossible gate condition.

    Detects:
    - Explicit worktree/isolation boundary refusal phrases
    - "cannot read" / "can't read" combined with an absolute path not under the
      execution cwd (the model is refusing to proceed because a required file
      lives outside the worktree — retrying will never help)
    """
    normalized = retry_reason.lower().strip()

    for phrase in _IMPOSSIBLE_GATE_PHRASES:
        if phrase in normalized:
            return True

    if "cannot read" in normalized or "can't read" in normalized:
        # Extract absolute Unix paths from the reason text.
        paths = re.findall(r'(?<![A-Za-z0-9])(/[\w./-]+)', retry_reason)
        try:
            cwd_resolved = Path(execution_cwd).resolve()
        except (OSError, ValueError):
            return False
        for path_str in paths:
            try:
                resolved = Path(path_str).resolve()
                resolved.relative_to(cwd_resolved)
            except (ValueError, OSError):
                # Path is not under execution cwd → impossible gate.
                return True

    return False
