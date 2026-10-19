#!/usr/bin/env python3
"""
Provider-neutral session handoff helper for Daplug.

Creates, validates, lists, and resumes compact, evidence-backed session
checkpoints without replaying full session transcripts or polluting tracked
repository state.

Usage:
    python3 handoff.py inspect [--cwd PATH] [--state-dir DIR] [--json]
    python3 handoff.py create --objective TEXT --next-action TEXT [options]
    python3 handoff.py resume [latest|PATH] [--cwd PATH] [--state-dir DIR] [--json]
    python3 handoff.py list [--cwd PATH] [--state-dir DIR] [--json]
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import tempfile
from typing import Any, Optional

SCHEMA_NAME = "daplug-handoff"
SCHEMA_VERSION = 1
SUPPORTED_SCHEMA_VERSIONS = frozenset({1})

DEFAULT_MAX_HANDOFF_BYTES = 16384  # 16 KiB total checkpoint budget
DEFAULT_MAX_SECTION_CHARS = 2500   # Per-section character budget
DEFAULT_MAX_CHANGED_FILES = 30     # Max auto-discovered git status paths listed

TRANSCRIPT_POLICY = "fallback_only_do_not_read_by_default"
TRANSCRIPT_FALLBACK_NOTICE = (
    "Transcript Policy (FALLBACK ONLY): Do NOT read or replay the full session "
    "transcript by default. Treat this handoff checkpoint as your primary working "
    "context and consult the transcript only as a last resort if a specific "
    "missing detail cannot be recovered from the repository or this document."
)

ALLOWED_VERIFICATION_STATUSES = (
    "not run",
    "unknown",
    "passed",
    "failed",
    "partial",
)

CANONICAL_SECTIONS: tuple[tuple[str, str], ...] = (
    ("objective", "Objective"),
    ("completed_work", "Completed Work"),
    ("decisions", "Decisions and Rationale"),
    ("constraints", "Constraints"),
    ("changed_files", "Changed Files"),
    ("verification", "Verification Evidence"),
    ("blockers", "Blockers / Unresolved Questions"),
    ("next_action", "Exact Next Action"),
)

SECTION_HEADING_TO_KEY: dict[str, str] = {
    "objective": "objective",
    "completed work": "completed_work",
    "decisions and rationale": "decisions",
    "decisions & rationale": "decisions",
    "constraints": "constraints",
    "changed files": "changed_files",
    "verification evidence": "verification",
    "blockers / unresolved questions": "blockers",
    "blockers and unresolved questions": "blockers",
    "exact next action": "next_action",
}

REQUIRED_METADATA_FIELDS: tuple[str, ...] = (
    "schema",
    "schema_version",
    "generated_at",
    "repo_id",
    "repo_root",
    "worktree_id",
    "worktree_path",
    "is_linked_worktree",
    "branch",
    "detached",
    "head_sha",
    "dirty_state",
    "is_dirty",
    "staged_count",
    "unstaged_count",
    "untracked_count",
    "dirty_entries_hash",
    "verification_status",
    "transcript_path",
    "transcript_policy",
    "size_budget_bytes",
)


class HandoffError(Exception):
    """Base error for handoff operations."""

    error_code = "handoff_error"

    def __init__(self, message: str, *, details: Optional[dict[str, Any]] = None) -> None:
        super().__init__(message)
        self.details: dict[str, Any] = details or {}

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "status": "error",
            "error_code": self.error_code,
            "error": str(self),
        }
        if self.details:
            payload["details"] = self.details
        return payload


class NotAGitRepositoryError(HandoffError):
    """Raised when the target directory is not inside a Git repository."""

    error_code = "not_git_repo"


class HandoffValidationError(HandoffError):
    """Base error for invalid or unusable handoff artifacts."""

    error_code = "validation_error"


class MissingHandoffError(HandoffValidationError):
    """Raised when a requested handoff artifact does not exist."""

    error_code = "missing"


class MalformedHandoffError(HandoffValidationError):
    """Raised when a handoff artifact is missing required metadata or sections."""

    error_code = "malformed"


class UnsupportedVersionError(HandoffValidationError):
    """Raised when a handoff artifact uses an unsupported schema version."""

    error_code = "unsupported_version"


class OversizedHandoffError(HandoffValidationError):
    """Raised when a handoff artifact exceeds its size budget."""

    error_code = "oversized"


class WrongRepositoryError(HandoffValidationError):
    """Raised when a handoff artifact belongs to a different Git repository."""

    error_code = "wrong_repository"


@dataclass(frozen=True)
class VerificationRecord:
    """Single command/test verification item with explicit status and evidence."""

    command: str
    status: str  # 'passed', 'failed', 'not run', 'unknown'
    evidence: str = ""

    def to_dict(self) -> dict[str, str]:
        return {
            "command": self.command,
            "status": self.status,
            "evidence": self.evidence,
        }


@dataclass(frozen=True)
class GitState:
    """Factual Git repository and worktree state."""

    repo_id: str
    repo_root: str
    git_common_dir: str
    git_dir: str
    worktree_id: str
    worktree_path: str
    is_linked_worktree: bool
    branch: Optional[str]
    detached: bool
    head_sha: str
    is_dirty: bool
    staged_count: int
    unstaged_count: int
    untracked_count: int
    conflict_count: int
    dirty_state: str
    dirty_entries_hash: str
    changed_files: list[str] = field(default_factory=list)
    transcript_path: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "repo_id": self.repo_id,
            "repo_root": self.repo_root,
            "git_common_dir": self.git_common_dir,
            "git_dir": self.git_dir,
            "worktree_id": self.worktree_id,
            "worktree_path": self.worktree_path,
            "is_linked_worktree": self.is_linked_worktree,
            "branch": self.branch,
            "detached": self.detached,
            "head_sha": self.head_sha,
            "is_dirty": self.is_dirty,
            "staged_count": self.staged_count,
            "unstaged_count": self.unstaged_count,
            "untracked_count": self.untracked_count,
            "conflict_count": self.conflict_count,
            "dirty_state": self.dirty_state,
            "dirty_entries_hash": self.dirty_entries_hash,
            "changed_files": list(self.changed_files),
            "transcript_path": self.transcript_path,
        }


@dataclass
class HandoffCheckpoint:
    """Canonical representation of a Daplug session handoff artifact."""

    schema: str
    schema_version: int
    generated_at: str
    repo_id: str
    repo_root: str
    worktree_id: str
    worktree_path: str
    is_linked_worktree: bool
    branch: Optional[str]
    detached: bool
    head_sha: str
    dirty_state: str
    is_dirty: bool
    staged_count: int
    unstaged_count: int
    untracked_count: int
    dirty_entries_hash: str
    verification_status: str
    transcript_path: Optional[str]
    transcript_policy: str
    size_budget_bytes: int
    objective: str
    completed_work: str
    decisions: str
    constraints: str
    changed_files: str
    verification: str
    blockers: str
    next_action: str

    def metadata_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "schema_version": self.schema_version,
            "generated_at": self.generated_at,
            "repo_id": self.repo_id,
            "repo_root": self.repo_root,
            "worktree_id": self.worktree_id,
            "worktree_path": self.worktree_path,
            "is_linked_worktree": self.is_linked_worktree,
            "branch": self.branch,
            "detached": self.detached,
            "head_sha": self.head_sha,
            "dirty_state": self.dirty_state,
            "is_dirty": self.is_dirty,
            "staged_count": self.staged_count,
            "unstaged_count": self.unstaged_count,
            "untracked_count": self.untracked_count,
            "dirty_entries_hash": self.dirty_entries_hash,
            "verification_status": self.verification_status,
            "transcript_path": self.transcript_path,
            "transcript_policy": self.transcript_policy,
            "size_budget_bytes": self.size_budget_bytes,
        }

    def sections_dict(self) -> dict[str, str]:
        return {
            "objective": self.objective,
            "completed_work": self.completed_work,
            "decisions": self.decisions,
            "constraints": self.constraints,
            "changed_files": self.changed_files,
            "verification": self.verification,
            "blockers": self.blockers,
            "next_action": self.next_action,
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "metadata": self.metadata_dict(),
            "sections": self.sections_dict(),
        }


@dataclass(frozen=True)
class DriftWarning:
    """Single state drift warning between checkpoint metadata and current Git state."""

    kind: str  # 'worktree', 'branch', 'head', 'dirty_state'
    recorded: str
    current: str
    message: str

    def to_dict(self) -> dict[str, str]:
        return {
            "kind": self.kind,
            "recorded": self.recorded,
            "current": self.current,
            "message": self.message,
        }


@dataclass
class ResumeReport:
    """Result of validating and comparing a handoff checkpoint against current Git state."""

    checkpoint_path: str
    checkpoint: HandoffCheckpoint
    current_git: GitState
    match_status: str  # 'exact_match' or 'drift_detected'
    safe_match: bool
    has_drift: bool
    drift_warnings: list[DriftWarning]
    summary: str
    exact_next_action: str
    transcript_fallback_notice: str
    content: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": "ok",
            "checkpoint_path": self.checkpoint_path,
            "match_status": self.match_status,
            "safe_match": self.safe_match,
            "has_drift": self.has_drift,
            "summary": self.summary,
            "drift_warnings": [w.to_dict() for w in self.drift_warnings],
            "exact_next_action": self.exact_next_action,
            "transcript_fallback_notice": self.transcript_fallback_notice,
            "metadata": self.checkpoint.metadata_dict(),
            "sections": self.checkpoint.sections_dict(),
            "current_git": self.current_git.to_dict(),
            "content": self.content,
        }


# ---------------------------------------------------------------------------
# Path Normalization & Storage Helpers
# ---------------------------------------------------------------------------


def _expand_home(raw: str, home: Optional[Path] = None) -> str:
    """Expand leading ~ using explicit home or Path.home() without hardcoding layouts."""
    if not raw.startswith("~"):
        return raw
    resolved_home = (home if home is not None else Path.home()).resolve(strict=False)
    if raw == "~":
        return str(resolved_home)
    if raw.startswith("~/") or raw.startswith("~\\"):
        return str(resolved_home / raw[2:])
    return os.path.expanduser(raw)


def normalize_path(
    path: Path | str,
    base_dir: Optional[Path | str] = None,
    home: Optional[Path] = None,
) -> Path:
    """Normalize a filesystem path without assuming a single home directory or repo layout."""
    raw = _expand_home(str(path).strip(), home=home)
    candidate = Path(raw)
    if not candidate.is_absolute() and base_dir is not None:
        base = normalize_path(base_dir, home=home)
        candidate = base / candidate
    return candidate.resolve(strict=False)


def normalize_path_str(
    path: Path | str,
    base_dir: Optional[Path | str] = None,
    home: Optional[Path] = None,
) -> str:
    """Return a canonical POSIX string representation of a normalized path."""
    return normalize_path(path, base_dir=base_dir, home=home).as_posix()


def slugify(value: str, max_words: int = 6, fallback: str = "checkpoint") -> str:
    """Convert arbitrary text into a safe, bounded filename slug."""
    cleaned = re.sub(r"[^a-zA-Z0-9]+", "-", value.lower()).strip("-")
    if not cleaned:
        return fallback
    words = [w for w in cleaned.split("-") if w][:max_words]
    result = "-".join(words)[:48].strip("-")
    return result or fallback


def derive_identity_id(canonical_path: str, prefix_name: str, fallback: str = "id") -> str:
    """Compute a deterministic `<slug>-<16-hex-sha256>` identifier from a canonical path."""
    safe_prefix = slugify(prefix_name, max_words=4, fallback=fallback)
    digest = hashlib.sha256(canonical_path.encode("utf-8")).hexdigest()[:16]
    return f"{safe_prefix}-{digest}"


def get_default_state_dir(
    state_dir: Optional[Path | str] = None,
    home: Optional[Path] = None,
) -> Path:
    """Resolve the untracked Daplug-owned handoff storage root directory.

    Priority:
    1. Explicit `state_dir` argument
    2. `DAPLUG_HANDOFF_DIR` environment variable
    3. `<home>/.claude/handoffs`
    """
    if state_dir is not None and str(state_dir).strip():
        return normalize_path(state_dir, home=home)
    env_dir = os.environ.get("DAPLUG_HANDOFF_DIR", "").strip()
    if env_dir:
        return normalize_path(env_dir, home=home)
    base_home = normalize_path(home if home is not None else Path.home())
    return base_home / ".claude" / "handoffs"


def get_worktree_store_dir(
    git_state: GitState,
    state_dir: Optional[Path | str] = None,
    home: Optional[Path] = None,
) -> Path:
    """Return the repository- and worktree-scoped checkpoint storage directory."""
    root = get_default_state_dir(state_dir=state_dir, home=home)
    return root / git_state.repo_id / git_state.worktree_id


def _chmod_best_effort(path: Path, mode: int) -> None:
    """Set POSIX permissions where supported."""
    try:
        os.chmod(path, mode)
    except (OSError, NotImplementedError):
        pass


def ensure_private_dir(directory: Path, mode: int = 0o700) -> Path:
    """Create a directory (and missing parents) with restrictive permissions."""
    directory.mkdir(parents=True, exist_ok=True, mode=mode)
    _chmod_best_effort(directory, mode)
    return directory


def atomic_write_text(
    target_path: Path,
    content: str,
    file_mode: int = 0o600,
    dir_mode: int = 0o700,
) -> Path:
    """Atomically write UTF-8 text to `target_path` with restrictive permissions."""
    resolved_target = target_path.resolve(strict=False)
    ensure_private_dir(resolved_target.parent, mode=dir_mode)
    data = content.encode("utf-8")

    fd, tmp_name = tempfile.mkstemp(
        prefix=f".{resolved_target.name}.",
        suffix=".tmp",
        dir=str(resolved_target.parent),
    )
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        _chmod_best_effort(tmp_path, file_mode)
        os.replace(tmp_path, resolved_target)
        _chmod_best_effort(resolved_target, file_mode)
    except Exception:
        try:
            if tmp_path.exists():
                tmp_path.unlink()
        except OSError:
            pass
        raise

    return resolved_target


# ---------------------------------------------------------------------------
# Secret Redaction
# ---------------------------------------------------------------------------

_SAFE_PLACEHOLDER_VALUES = frozenset(
    {
        "",
        "none",
        "null",
        "nil",
        "true",
        "false",
        "yes",
        "no",
        "enabled",
        "disabled",
        "unknown",
        "not_run",
        "not-run",
        "not_set",
        "not-set",
        "unset",
        "redacted",
        "placeholder",
        "example",
        "dummy",
    }
)

_PEM_PRIVATE_KEY_RE = re.compile(
    r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z0-9 ]*PRIVATE KEY-----"
)
_AUTH_HEADER_RE = re.compile(
    r"(?i)(\bauthorization\s*[:=]\s*(?:bearer|basic|token|digest)\s+)([^\s\"'`,;]+)"
)
_BEARER_TOKEN_RE = re.compile(
    r"(?i)(\bbearer\s+)([A-Za-z0-9._~+/=-]{14,})"
)
_URL_CREDENTIALS_RE = re.compile(
    r"(https?://[^/\s:@\"']+:)(?!\[REDACTED)([^@\s/\"']+)(@)"
)
_TOKEN_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (
        re.compile(r"\bsk-(?:proj-|ant-|live-|test-)?[A-Za-z0-9_-]{12,}\b"),
        "[REDACTED:API_KEY]",
    ),
    (
        re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9_]{16,}|github_pat_[A-Za-z0-9_]{16,})\b"),
        "[REDACTED:GITHUB_TOKEN]",
    ),
    (
        re.compile(r"\bglpat-[A-Za-z0-9_-]{12,}\b"),
        "[REDACTED:GITLAB_TOKEN]",
    ),
    (
        re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b"),
        "[REDACTED:AWS_KEY]",
    ),
    (
        re.compile(r"\bxox[bparos]-[A-Za-z0-9-]{10,}\b"),
        "[REDACTED:SLACK_TOKEN]",
    ),
    (
        re.compile(r"\bAIza[A-Za-z0-9_-]{20,}\b"),
        "[REDACTED:GOOGLE_KEY]",
    ),
    (
        re.compile(r"\bhf_[A-Za-z0-9]{16,}\b"),
        "[REDACTED:HF_TOKEN]",
    ),
    (
        re.compile(r"\bnpm_[A-Za-z0-9]{16,}\b"),
        "[REDACTED:NPM_TOKEN]",
    ),
    (
        re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b"),
        "[REDACTED:JWT]",
    ),
)

_SENSITIVE_KV_RE = re.compile(
    r"(?i)\b([A-Za-z0-9_.-]*(?:api[_-]?key|client[_-]?secret|private[_-]?key|"
    r"access[_-]?key|secret[_-]?key|auth[_-]?token|access[_-]?token|refresh[_-]?token|"
    r"session[_-]?token|bearer[_-]?token|password|passwd|secret|token|credentials?)"
    r"[A-Za-z0-9_.-]*)\s*([:=])\s*(\"[^\"]*\"|'[^']*'|[^\s,;#'\")\]]+)"
)


def _is_safe_kv_value(raw_value: str) -> bool:
    unquoted = raw_value.strip().strip("\"'").strip()
    lower = unquoted.lower()
    if lower in _SAFE_PLACEHOLDER_VALUES:
        return True
    if unquoted.startswith("[REDACTED") and unquoted.endswith("]"):
        return True
    if unquoted.startswith("<") and unquoted.endswith(">"):
        return True
    if unquoted.startswith("${") and unquoted.endswith("}"):
        return True
    return False


def redact_secrets(text: str) -> tuple[str, int]:
    """Conservatively redact common credential formats and secret assignments.

    Returns:
        (redacted_text, redaction_count)
    """
    if not text:
        return text, 0

    count = 0
    current = text

    current, n = _PEM_PRIVATE_KEY_RE.subn("[REDACTED:PRIVATE_KEY]", current)
    count += n

    current, n = _URL_CREDENTIALS_RE.subn(r"\1[REDACTED:URL_SECRET]\3", current)
    count += n

    current, n = _AUTH_HEADER_RE.subn(r"\1[REDACTED:TOKEN]", current)
    count += n

    def _replace_bearer(match: re.Match[str]) -> str:
        nonlocal count
        token_val = match.group(2)
        if token_val.startswith("[REDACTED"):
            return match.group(0)
        count += 1
        return f"{match.group(1)}[REDACTED:TOKEN]"

    current = _BEARER_TOKEN_RE.sub(_replace_bearer, current)

    for pattern, replacement in _TOKEN_PATTERNS:
        current, n = pattern.subn(replacement, current)
        count += n

    def _replace_kv(match: re.Match[str]) -> str:
        nonlocal count
        key = match.group(1)
        sep = match.group(2)
        val = match.group(3)
        if _is_safe_kv_value(val):
            return match.group(0)
        count += 1
        spacing = " " if sep == ":" else ""
        return f"{key}{sep}{spacing}[REDACTED:SECRET]"

    current = _SENSITIVE_KV_RE.sub(_replace_kv, current)
    return current, count


# ---------------------------------------------------------------------------
# Transcript Path Discovery (via prompt-manager when available)
# ---------------------------------------------------------------------------


def detect_transcript_path(
    worktree_path: Path,
    repo_root: Path,
    claude_home: Optional[Path] = None,
    home: Optional[Path] = None,
) -> Optional[str]:
    """Detect the current session transcript path without reading its contents."""
    manager_script = (
        Path(__file__).resolve().parents[2]
        / "prompt-manager"
        / "scripts"
        / "manager.py"
    )
    resolved_claude_home = claude_home
    if resolved_claude_home is None:
        base_home = normalize_path(home if home is not None else Path.home())
        resolved_claude_home = base_home / ".claude"

    if manager_script.is_file():
        try:
            spec = importlib.util.spec_from_file_location(
                "daplug_prompt_manager", manager_script
            )
            if spec and spec.loader:
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                found = module.get_session_file(
                    cwd=worktree_path,
                    repo_root=repo_root,
                    claude_home=resolved_claude_home,
                )
                if found is not None:
                    redacted, _ = redact_secrets(normalize_path_str(found, home=home))
                    return redacted
        except Exception:
            pass

    return None


# ---------------------------------------------------------------------------
# Factual Git State Inspection
# ---------------------------------------------------------------------------


def _run_git(cwd: Path, args: list[str]) -> subprocess.CompletedProcess[str]:
    """Run a read-only git command in `cwd`."""
    try:
        return subprocess.run(
            ["git", "-C", str(cwd), *args],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError as exc:
        raise NotAGitRepositoryError(
            f"Unable to run git in '{cwd}': {exc}",
            details={"cwd": str(cwd)},
        ) from exc


def _resolve_git_dir_path(worktree_path: Path, flag: str) -> Path:
    """Resolve `--git-dir` or `--git-common-dir` to a normalized absolute Path."""
    res = _run_git(worktree_path, ["rev-parse", "--path-format=absolute", flag])
    if res.returncode == 0 and res.stdout.strip():
        return normalize_path(res.stdout.strip(), base_dir=worktree_path)

    fallback = _run_git(worktree_path, ["rev-parse", flag])
    if fallback.returncode != 0 or not fallback.stdout.strip():
        raise NotAGitRepositoryError(
            f"Failed to resolve Git '{flag}' in '{worktree_path}'",
            details={"cwd": str(worktree_path), "stderr": fallback.stderr.strip()},
        )
    return normalize_path(fallback.stdout.strip(), base_dir=worktree_path)


def _parse_porcelain_z(
    raw_output: str,
    max_changed_files: int = DEFAULT_MAX_CHANGED_FILES,
) -> tuple[int, int, int, int, str, list[str]]:
    """Parse `git status --porcelain=v1 -z -uall` output safely (including paths with spaces)."""
    if not raw_output:
        return 0, 0, 0, 0, "clean", []

    tokens = raw_output.split("\0")
    staged = 0
    unstaged = 0
    untracked = 0
    conflicts = 0
    canonical_entries: list[str] = []
    formatted_files: list[str] = []

    idx = 0
    total_tokens = len(tokens)
    while idx < total_tokens:
        entry = tokens[idx]
        idx += 1
        if not entry or len(entry) < 3:
            continue

        xy = entry[:2]
        path = entry[3:]
        x_code, y_code = xy[0], xy[1]

        orig_path: Optional[str] = None
        if x_code in ("R", "C") or y_code in ("R", "C"):
            if idx < total_tokens and tokens[idx]:
                orig_path = tokens[idx]
                idx += 1

        if xy == "??":
            untracked += 1
            tag = "untracked"
        elif xy == "!!":
            continue
        else:
            is_conflict = (
                "U" in xy
                or xy in ("DD", "AA", "AU", "UA", "DU", "UD", "UU")
            )
            if is_conflict:
                conflicts += 1
            if x_code not in (" ", "?", "!"):
                staged += 1
            if y_code not in (" ", "?", "!"):
                unstaged += 1

            tags: list[str] = []
            if is_conflict:
                tags.append("conflict")
            if x_code not in (" ", "?", "!"):
                tags.append("staged")
            if y_code not in (" ", "?", "!"):
                tags.append("unstaged")
            tag = ", ".join(tags) if tags else "modified"

        display_path = f"{orig_path} -> {path}" if orig_path else path
        canonical_entries.append(f"{xy} {display_path}")
        formatted_files.append(f"{xy.strip() or 'M'} {display_path} ({tag})")

    if not canonical_entries:
        return 0, 0, 0, 0, "clean", []

    canonical_sorted = "\n".join(sorted(canonical_entries))
    entries_hash = hashlib.sha256(canonical_sorted.encode("utf-8")).hexdigest()[:16]

    if len(formatted_files) > max_changed_files:
        overflow = len(formatted_files) - max_changed_files
        bounded = formatted_files[:max_changed_files] + [
            f"... and {overflow} more working-tree path(s) (run `git status` for full list)"
        ]
    else:
        bounded = formatted_files

    return staged, unstaged, untracked, conflicts, entries_hash, bounded


def inspect_git_state(
    cwd: Optional[Path | str] = None,
    *,
    transcript_path: Optional[str] = None,
    detect_transcript: bool = True,
    claude_home: Optional[Path] = None,
    home: Optional[Path] = None,
    max_changed_files: int = DEFAULT_MAX_CHANGED_FILES,
) -> GitState:
    """Inspect factual Git state for the repository or linked worktree at `cwd`."""
    target_cwd = normalize_path(cwd if cwd is not None else Path.cwd(), home=home)
    if not target_cwd.exists() or not target_cwd.is_dir():
        raise NotAGitRepositoryError(
            f"Working directory does not exist or is not a directory: {target_cwd}",
            details={"cwd": target_cwd.as_posix()},
        )

    top_res = _run_git(target_cwd, ["rev-parse", "--show-toplevel"])
    if top_res.returncode != 0 or not top_res.stdout.strip():
        raise NotAGitRepositoryError(
            f"Not inside a Git repository: {target_cwd.as_posix()}",
            details={
                "cwd": target_cwd.as_posix(),
                "stderr": top_res.stderr.strip(),
            },
        )

    worktree_path = normalize_path(top_res.stdout.strip(), base_dir=target_cwd, home=home)
    git_common_dir = _resolve_git_dir_path(worktree_path, "--git-common-dir")
    git_dir = _resolve_git_dir_path(worktree_path, "--git-dir")

    if git_common_dir.name == ".git":
        repo_root = git_common_dir.parent
    else:
        repo_root = git_common_dir

    repo_common_posix = git_common_dir.as_posix()
    repo_root_posix = repo_root.as_posix()
    worktree_posix = worktree_path.as_posix()

    repo_id = derive_identity_id(repo_common_posix, repo_root.name or "repo", fallback="repo")
    worktree_id = derive_identity_id(
        worktree_posix, worktree_path.name or "worktree", fallback="worktree"
    )
    is_linked_worktree = git_dir.as_posix() != repo_common_posix

    branch_res = _run_git(worktree_path, ["symbolic-ref", "--quiet", "--short", "HEAD"])
    if branch_res.returncode == 0 and branch_res.stdout.strip():
        branch: Optional[str] = branch_res.stdout.strip()
        detached = False
    else:
        branch = None
        detached = True

    head_res = _run_git(worktree_path, ["rev-parse", "--verify", "HEAD"])
    if head_res.returncode == 0 and head_res.stdout.strip():
        head_sha = head_res.stdout.strip()
    else:
        head_sha = "UNBORN"

    status_res = _run_git(worktree_path, ["status", "--porcelain=v1", "-z", "-uall"])
    staged, unstaged, untracked, conflicts, entries_hash, changed_files = _parse_porcelain_z(
        status_res.stdout if status_res.returncode == 0 else "",
        max_changed_files=max_changed_files,
    )

    is_dirty = bool(staged or unstaged or untracked or conflicts)
    summary_parts = [
        f"{staged} staged",
        f"{unstaged} unstaged",
        f"{untracked} untracked",
    ]
    if conflicts:
        summary_parts.append(f"{conflicts} conflicted")
    state_label = "dirty" if is_dirty else "clean"
    dirty_state = f"{state_label} ({', '.join(summary_parts)})"

    resolved_transcript: Optional[str] = None
    if transcript_path is not None and str(transcript_path).strip():
        norm_transcript = normalize_path_str(transcript_path, base_dir=worktree_path, home=home)
        resolved_transcript, _ = redact_secrets(norm_transcript)
    elif detect_transcript:
        resolved_transcript = detect_transcript_path(
            worktree_path=worktree_path,
            repo_root=repo_root,
            claude_home=claude_home,
            home=home,
        )

    return GitState(
        repo_id=repo_id,
        repo_root=repo_root_posix,
        git_common_dir=repo_common_posix,
        git_dir=git_dir.as_posix(),
        worktree_id=worktree_id,
        worktree_path=worktree_posix,
        is_linked_worktree=is_linked_worktree,
        branch=branch,
        detached=detached,
        head_sha=head_sha,
        is_dirty=is_dirty,
        staged_count=staged,
        unstaged_count=unstaged,
        untracked_count=untracked,
        conflict_count=conflicts,
        dirty_state=dirty_state,
        dirty_entries_hash=entries_hash,
        changed_files=changed_files,
        transcript_path=resolved_transcript,
    )


# ---------------------------------------------------------------------------
# Verification Section & Section Formatting Helpers
# ---------------------------------------------------------------------------

_UNVERIFIED_PASS_CLAIM_RE = re.compile(
    r"(?i)\b(?:all\s+(?:unit\s+|integration\s+)?tests?\s+pass(?:ed|ing)?|"
    r"tests?\s+pass(?:ed|ing)?|suite\s+pass(?:ed|ing)?|build\s+pass(?:ed|ing)?|"
    r"verified\s+green|everything\s+passes|100%\s+pass(?:ed|ing)?)\b"
)
_RAW_DIFF_RE = re.compile(
    r"(?m)^\s*(?:[-*]\s+)?(?:diff --git a/.+ b/.+|@@ -\d+(?:,\d+)? \+\d+(?:,\d+)? @@)"
)


def parse_verification_item(raw: str | dict[str, Any] | VerificationRecord) -> VerificationRecord:
    """Parse a verification item from `command :: status :: evidence`, dict, or VerificationRecord."""
    if isinstance(raw, VerificationRecord):
        cmd, status, evidence = raw.command, raw.status, raw.evidence
    elif isinstance(raw, dict):
        cmd = str(raw.get("command", "")).strip()
        status = str(raw.get("status", "unknown")).strip().lower()
        evidence = str(raw.get("evidence", "")).strip()
    else:
        text = str(raw).strip()
        if "::" in text:
            parts = [p.strip() for p in text.split("::", 2)]
            cmd = parts[0]
            status = parts[1].lower() if len(parts) > 1 and parts[1] else "unknown"
            evidence = parts[2] if len(parts) > 2 else ""
        else:
            # Free-form verification note without structured `command :: status :: evidence`
            cmd = ""
            status = "unknown"
            evidence = text

    if status not in ALLOWED_VERIFICATION_STATUSES or status == "partial":
        status = "unknown"

    # Never allow a 'passed' status unless both a command and concrete evidence are present.
    if status == "passed" and (not cmd or not evidence):
        status = "unknown"
        if not evidence:
            evidence = "Pass claim downgraded to unknown because no command/output evidence was supplied."
        elif not cmd:
            evidence = (
                "Pass claim downgraded to unknown because no verification command was recorded: "
                f"{evidence}"
            )

    # If free-form text claims tests passed without a structured command + evidence pair, neutralize it.
    if status in ("unknown", "not run") and not cmd and _UNVERIFIED_PASS_CLAIM_RE.search(evidence):
        status = "unknown"
        evidence = (
            "Unverified pass claim omitted (status set to unknown because no concrete "
            "command or output evidence was supplied during this session)."
        )

    return VerificationRecord(command=cmd, status=status, evidence=evidence)


def build_verification_section(
    verification_items: Optional[list[str | dict[str, Any] | VerificationRecord]] = None,
    requested_status: Optional[str] = None,
) -> tuple[str, str]:
    """Build the `verification_status` metadata value and `## Verification Evidence` body.

    Enforces Requirement 2: never claim a test or command passed unless actual
    evidence is supplied in the handoff; use explicit `not run`/`unknown` states otherwise.
    """
    records = [parse_verification_item(item) for item in (verification_items or []) if str(item).strip()]

    req = requested_status.strip().lower() if requested_status else None
    if req and req not in ALLOWED_VERIFICATION_STATUSES:
        raise MalformedHandoffError(
            f"Invalid verification_status '{requested_status}'. Allowed: {ALLOWED_VERIFICATION_STATUSES}"
        )

    if not records:
        if req == "passed":
            # Never claim passed without actual evidence.
            status = "unknown"
            body = (
                "- **Status**: `unknown`\n"
                "- **Details**: Pass status was requested without verification evidence; "
                "downgraded to `unknown`."
            )
            return status, body
        status = req if req in ("not run", "unknown", "failed") else "not run"
        body = (
            f"- **Status**: `{status}`\n"
            f"- **Details**: No verification commands or test evidence recorded during this session."
        )
        return status, body

    statuses = [r.status for r in records]
    has_passed_with_evidence = any(r.status == "passed" and r.command and r.evidence for r in records)
    has_failed = any(s == "failed" for s in statuses)
    all_passed = all(r.status == "passed" and r.command and r.evidence for r in records)
    all_not_run = all(s == "not run" for s in statuses)

    if has_failed:
        computed_status = "failed"
    elif all_passed:
        computed_status = "passed"
    elif has_passed_with_evidence:
        computed_status = "partial"
    elif all_not_run:
        computed_status = "not run"
    else:
        computed_status = "unknown"

    if req is not None:
        if req == "passed" and not all_passed:
            # Refuse to claim overall 'passed' if any item lacks evidence or did not pass.
            computed_status = "partial" if has_passed_with_evidence else "unknown"
        elif req in ("failed", "not run", "unknown", "partial") and req != "passed":
            if req == "not run" and has_passed_with_evidence:
                computed_status = "partial"
            elif not has_failed:
                computed_status = req

    lines = [f"- **Overall Status**: `{computed_status}`"]
    for rec in records:
        if rec.command:
            detail = f" — {rec.evidence}" if rec.evidence else " — no output evidence recorded"
            lines.append(f"- `[{rec.status}]` `{rec.command}`{detail}")
        else:
            lines.append(f"- `[{rec.status}]` {rec.evidence or 'No details provided.'}")

    return computed_status, "\n".join(lines)


def _format_bullet_section(items: str | list[str] | None, default_text: str) -> str:
    """Format a string or list of strings into a clean Markdown section body."""
    if items is None:
        return f"- {default_text}"
    if isinstance(items, str):
        stripped = items.strip()
        if not stripped:
            return f"- {default_text}"
        lines = [line.rstrip() for line in stripped.splitlines() if line.strip()]
    else:
        lines = []
        for entry in items:
            for subline in str(entry).splitlines():
                if subline.strip():
                    lines.append(subline.strip())
    if not lines:
        return f"- {default_text}"

    formatted: list[str] = []
    for line in lines:
        if line.startswith(("- ", "* ", "> ")) or re.match(r"^\d+[.)]\s+", line):
            formatted.append(line)
        else:
            formatted.append(f"- {line}")
    return "\n".join(formatted)


def _format_changed_files_section(
    git_changed_files: list[str],
    extra_changed_files: Optional[list[str] | str] = None,
    head_sha: str = "",
) -> str:
    """Combine factual Git working-tree changed files with optional extra annotations."""
    entries: list[str] = []
    seen: set[str] = set()

    for item in git_changed_files:
        cleaned = item.strip()
        if cleaned and cleaned not in seen:
            seen.add(cleaned)
            entries.append(f"- `{cleaned}`" if not cleaned.startswith("...") else f"- {cleaned}")

    if extra_changed_files:
        raw_list = (
            [extra_changed_files]
            if isinstance(extra_changed_files, str)
            else list(extra_changed_files)
        )
        for raw in raw_list:
            for sub in str(raw).splitlines():
                cleaned = sub.strip().lstrip("-* ").strip()
                if cleaned and cleaned not in seen:
                    seen.add(cleaned)
                    entries.append(f"- {cleaned}")

    if not entries:
        short_head = head_sha[:12] if head_sha and head_sha != "UNBORN" else (head_sha or "unknown")
        return f"- No uncommitted working-tree changes (working tree clean at HEAD `{short_head}`)."

    return "\n".join(entries)


def _validate_section_constraints(
    sections: dict[str, str],
    max_section_chars: int = DEFAULT_MAX_SECTION_CHARS,
) -> None:
    """Ensure sections are non-empty, contain no raw diffs, and stay within per-section bounds."""
    for key, title in CANONICAL_SECTIONS:
        content = sections.get(key, "").strip()
        if not content:
            raise MalformedHandoffError(
                f"Required section '{title}' ({key}) is missing or empty.",
                details={"section": key, "title": title},
            )
        if _RAW_DIFF_RE.search(content):
            raise OversizedHandoffError(
                f"Section '{title}' contains raw unified diff output. "
                "Summarize file changes instead of embedding full diffs.",
                details={"section": key, "title": title},
            )
        if len(content) > max_section_chars:
            raise OversizedHandoffError(
                f"Section '{title}' is {len(content)} characters, exceeding the per-section "
                f"limit of {max_section_chars} characters. Compact '{title}' instead of truncating.",
                details={
                    "section": key,
                    "title": title,
                    "section_chars": len(content),
                    "max_section_chars": max_section_chars,
                },
            )


# ---------------------------------------------------------------------------
# Rendering & Parsing (Canonical Schema)
# ---------------------------------------------------------------------------


def _serialize_frontmatter_value(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    return json.dumps(str(value), ensure_ascii=False)


def _parse_frontmatter_value(raw: str) -> Any:
    token = raw.strip()
    if not token or token in ("null", "~", "None"):
        return None
    if token == "true":
        return True
    if token == "false":
        return False
    try:
        return json.loads(token)
    except json.JSONDecodeError:
        # Support unquoted strings in hand-crafted fixtures (e.g. `schema: daplug-handoff`)
        if (token.startswith('"') and token.endswith('"')) or (
            token.startswith("'") and token.endswith("'")
        ):
            return token[1:-1]
        return token


def render_handoff(
    checkpoint: HandoffCheckpoint,
    *,
    max_bytes: Optional[int] = None,
    max_section_chars: Optional[int] = None,
) -> str:
    """Serialize a `HandoffCheckpoint` into its canonical Markdown representation."""
    effective_max_bytes = (
        max_bytes
        if max_bytes is not None
        else (checkpoint.size_budget_bytes or DEFAULT_MAX_HANDOFF_BYTES)
    )
    if effective_max_bytes <= 0:
        raise OversizedHandoffError(
            f"Invalid size_budget_bytes: {effective_max_bytes}",
            details={"size_budget_bytes": effective_max_bytes},
        )

    effective_section_chars = (
        max_section_chars
        if max_section_chars is not None
        else min(DEFAULT_MAX_SECTION_CHARS, max(200, effective_max_bytes // 2))
    )

    sections = checkpoint.sections_dict()
    _validate_section_constraints(sections, max_section_chars=effective_section_chars)

    meta = checkpoint.metadata_dict()
    meta["size_budget_bytes"] = effective_max_bytes

    frontmatter_lines = ["---"]
    for field_name in REQUIRED_METADATA_FIELDS:
        frontmatter_lines.append(
            f"{field_name}: {_serialize_frontmatter_value(meta.get(field_name))}"
        )
    frontmatter_lines.append("---")

    branch_display = (
        f"DETACHED HEAD"
        if checkpoint.detached
        else (checkpoint.branch or "DETACHED HEAD")
    )
    transcript_display = checkpoint.transcript_path or "not detected"

    body_lines = [
        *frontmatter_lines,
        "",
        "# Daplug Session Handoff",
        "",
        "## Repository & Session State",
        f"- **Generated At**: `{checkpoint.generated_at}`",
        f"- **Repository ID**: `{checkpoint.repo_id}`",
        f"- **Repository Root**: `{checkpoint.repo_root}`",
        f"- **Worktree Path**: `{checkpoint.worktree_path}`",
        f"- **Linked Worktree**: `{'yes' if checkpoint.is_linked_worktree else 'no'}`",
        f"- **Branch / HEAD State**: `{branch_display}`",
        f"- **HEAD SHA**: `{checkpoint.head_sha}`",
        f"- **Working Tree Status**: `{checkpoint.dirty_state}`",
        f"- **Verification Status**: `{checkpoint.verification_status}`",
        f"- **Session Transcript (Fallback Only)**: `{transcript_display}`",
        f"  > **{TRANSCRIPT_FALLBACK_NOTICE}**",
        "",
    ]

    for key, heading in CANONICAL_SECTIONS:
        body_lines.append(f"## {heading}")
        body_lines.append(sections[key].strip())
        body_lines.append("")

    rendered = "\n".join(body_lines).rstrip() + "\n"
    encoded_size = len(rendered.encode("utf-8"))
    if encoded_size > effective_max_bytes:
        raise OversizedHandoffError(
            f"Rendered handoff is {encoded_size} bytes, exceeding the size budget of "
            f"{effective_max_bytes} bytes. Compact section content rather than truncating.",
            details={
                "size_bytes": encoded_size,
                "size_budget_bytes": effective_max_bytes,
            },
        )
    return rendered


def parse_handoff(
    content: str,
    *,
    max_bytes: int = DEFAULT_MAX_HANDOFF_BYTES,
) -> HandoffCheckpoint:
    """Parse and validate a Markdown handoff artifact into a `HandoffCheckpoint`."""
    if not isinstance(content, str) or not content.strip():
        raise MalformedHandoffError("Handoff artifact is empty.")

    raw_bytes_len = len(content.encode("utf-8"))
    if raw_bytes_len > max_bytes:
        raise OversizedHandoffError(
            f"Handoff artifact is {raw_bytes_len} bytes, exceeding maximum allowed "
            f"{max_bytes} bytes.",
            details={"size_bytes": raw_bytes_len, "max_bytes": max_bytes},
        )

    if not content.startswith("---\n") and not content.startswith("---\r\n"):
        raise MalformedHandoffError(
            "Handoff artifact is missing required YAML frontmatter header ('---')."
        )

    fm_match = re.match(r"^---\r?\n(.*?)\r?\n---\r?\n(.*)$", content, flags=re.DOTALL)
    if not fm_match:
        raise MalformedHandoffError(
            "Handoff artifact has unterminated YAML frontmatter header."
        )

    fm_block, markdown_body = fm_match.group(1), fm_match.group(2)
    metadata: dict[str, Any] = {}

    stripped_fm = fm_block.strip()
    if stripped_fm.startswith("{") and stripped_fm.endswith("}"):
        try:
            loaded = json.loads(stripped_fm)
            if not isinstance(loaded, dict):
                raise MalformedHandoffError("Frontmatter JSON must be an object.")
            metadata = loaded
        except json.JSONDecodeError as exc:
            raise MalformedHandoffError(f"Malformed frontmatter JSON: {exc}") from exc
    else:
        for line_no, raw_line in enumerate(fm_block.splitlines(), start=1):
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            if ":" not in line:
                raise MalformedHandoffError(
                    f"Malformed frontmatter line {line_no}: {raw_line!r}"
                )
            key, _, raw_val = line.partition(":")
            key = key.strip()
            if not key:
                raise MalformedHandoffError(
                    f"Empty frontmatter key on line {line_no}"
                )
            metadata[key] = _parse_frontmatter_value(raw_val)

    schema_name = metadata.get("schema")
    if schema_name != SCHEMA_NAME:
        raise MalformedHandoffError(
            f"Invalid or missing handoff schema: expected '{SCHEMA_NAME}', got {schema_name!r}."
        )

    if "schema_version" not in metadata or metadata["schema_version"] is None:
        raise MalformedHandoffError("Missing required 'schema_version' in handoff metadata.")

    version = metadata["schema_version"]
    if isinstance(version, bool) or not isinstance(version, int):
        try:
            version = int(str(version))
        except (ValueError, TypeError) as exc:
            raise MalformedHandoffError(
                f"Invalid non-integer schema_version: {metadata['schema_version']!r}"
            ) from exc

    if version not in SUPPORTED_SCHEMA_VERSIONS:
        raise UnsupportedVersionError(
            f"Unsupported handoff schema_version {version}. Supported versions: "
            f"{sorted(SUPPORTED_SCHEMA_VERSIONS)}.",
            details={
                "schema_version": version,
                "supported_versions": sorted(SUPPORTED_SCHEMA_VERSIONS),
            },
        )

    missing_meta = [
        field_name
        for field_name in REQUIRED_METADATA_FIELDS
        if field_name not in metadata
    ]
    if missing_meta:
        raise MalformedHandoffError(
            f"Handoff metadata is missing required field(s): {', '.join(missing_meta)}",
            details={"missing_fields": missing_meta},
        )

    # Validate field types
    for str_field in (
        "generated_at",
        "repo_id",
        "repo_root",
        "worktree_id",
        "worktree_path",
        "head_sha",
        "dirty_state",
        "dirty_entries_hash",
        "verification_status",
        "transcript_policy",
    ):
        val = metadata.get(str_field)
        if not isinstance(val, str) or not val.strip():
            raise MalformedHandoffError(
                f"Metadata field '{str_field}' must be a non-empty string."
            )

    for bool_field in ("is_linked_worktree", "detached", "is_dirty"):
        if not isinstance(metadata.get(bool_field), bool):
            raise MalformedHandoffError(
                f"Metadata field '{bool_field}' must be a boolean."
            )

    for int_field in ("staged_count", "unstaged_count", "untracked_count", "size_budget_bytes"):
        val = metadata.get(int_field)
        if isinstance(val, bool) or not isinstance(val, int) or val < 0:
            raise MalformedHandoffError(
                f"Metadata field '{int_field}' must be a non-negative integer."
            )

    if metadata["verification_status"] not in ALLOWED_VERIFICATION_STATUSES:
        raise MalformedHandoffError(
            f"Invalid verification_status {metadata['verification_status']!r} in metadata."
        )

    recorded_budget = int(metadata["size_budget_bytes"])
    if recorded_budget <= 0 or raw_bytes_len > recorded_budget:
        raise OversizedHandoffError(
            f"Handoff artifact size ({raw_bytes_len} bytes) exceeds its recorded "
            f"size_budget_bytes ({recorded_budget} bytes).",
            details={"size_bytes": raw_bytes_len, "size_budget_bytes": recorded_budget},
        )

    branch_val = metadata.get("branch")
    if branch_val is not None and not isinstance(branch_val, str):
        raise MalformedHandoffError("Metadata field 'branch' must be a string or null.")
    if metadata["detached"] and branch_val:
        # Normalize detached branch representation
        branch_val = None
    if not metadata["detached"] and not branch_val:
        raise MalformedHandoffError(
            "Metadata field 'branch' must be non-empty when 'detached' is false."
        )

    transcript_val = metadata.get("transcript_path")
    if transcript_val is not None and not isinstance(transcript_val, str):
        raise MalformedHandoffError(
            "Metadata field 'transcript_path' must be a string or null."
        )

    # Parse `## <Heading>` sections from Markdown body
    heading_matches = list(re.finditer(r"(?m)^##\s+(.+?)\s*$", markdown_body))
    if not heading_matches:
        raise MalformedHandoffError(
            "Handoff artifact body contains no level-2 ('## ') section headings."
        )

    extracted_sections: dict[str, str] = {}
    for idx, match in enumerate(heading_matches):
        heading_text = match.group(1).strip().lower()
        section_start = match.end()
        section_end = (
            heading_matches[idx + 1].start()
            if idx + 1 < len(heading_matches)
            else len(markdown_body)
        )
        section_body = markdown_body[section_start:section_end].strip()
        canonical_key = SECTION_HEADING_TO_KEY.get(heading_text)
        if canonical_key:
            extracted_sections[canonical_key] = section_body

    missing_sections = [
        title
        for key, title in CANONICAL_SECTIONS
        if key not in extracted_sections or not extracted_sections[key].strip()
    ]
    if missing_sections:
        raise MalformedHandoffError(
            f"Handoff artifact is missing required section(s): {', '.join(missing_sections)}",
            details={"missing_sections": missing_sections},
        )

    _validate_section_constraints(
        extracted_sections,
        max_section_chars=max(DEFAULT_MAX_SECTION_CHARS, recorded_budget),
    )

    return HandoffCheckpoint(
        schema=SCHEMA_NAME,
        schema_version=version,
        generated_at=metadata["generated_at"],
        repo_id=metadata["repo_id"],
        repo_root=metadata["repo_root"],
        worktree_id=metadata["worktree_id"],
        worktree_path=metadata["worktree_path"],
        is_linked_worktree=metadata["is_linked_worktree"],
        branch=branch_val,
        detached=metadata["detached"],
        head_sha=metadata["head_sha"],
        dirty_state=metadata["dirty_state"],
        is_dirty=metadata["is_dirty"],
        staged_count=metadata["staged_count"],
        unstaged_count=metadata["unstaged_count"],
        untracked_count=metadata["untracked_count"],
        dirty_entries_hash=metadata["dirty_entries_hash"],
        verification_status=metadata["verification_status"],
        transcript_path=transcript_val,
        transcript_policy=metadata["transcript_policy"],
        size_budget_bytes=recorded_budget,
        objective=extracted_sections["objective"],
        completed_work=extracted_sections["completed_work"],
        decisions=extracted_sections["decisions"],
        constraints=extracted_sections["constraints"],
        changed_files=extracted_sections["changed_files"],
        verification=extracted_sections["verification"],
        blockers=extracted_sections["blockers"],
        next_action=extracted_sections["next_action"],
    )


def load_handoff_file(
    path: Path | str,
    *,
    max_bytes: int = DEFAULT_MAX_HANDOFF_BYTES,
    base_dir: Optional[Path | str] = None,
    home: Optional[Path] = None,
) -> tuple[Path, str, HandoffCheckpoint]:
    """Load, size-check, and parse a handoff file from disk without reading unbounded files."""
    resolved = normalize_path(path, base_dir=base_dir, home=home)
    if not resolved.exists():
        raise MissingHandoffError(
            f"Handoff checkpoint not found: {resolved.as_posix()}",
            details={"path": resolved.as_posix()},
        )
    if not resolved.is_file():
        raise MalformedHandoffError(
            f"Handoff path is not a regular file: {resolved.as_posix()}",
            details={"path": resolved.as_posix()},
        )

    try:
        file_size = resolved.stat().st_size
    except OSError as exc:
        raise MissingHandoffError(
            f"Unable to stat handoff checkpoint '{resolved.as_posix()}': {exc}",
            details={"path": resolved.as_posix()},
        ) from exc

    if file_size > max_bytes:
        raise OversizedHandoffError(
            f"Handoff checkpoint '{resolved.as_posix()}' is {file_size} bytes, exceeding "
            f"the size budget of {max_bytes} bytes.",
            details={
                "path": resolved.as_posix(),
                "size_bytes": file_size,
                "max_bytes": max_bytes,
            },
        )

    try:
        raw_content = resolved.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise MalformedHandoffError(
            f"Handoff checkpoint '{resolved.as_posix()}' is not valid UTF-8 text.",
            details={"path": resolved.as_posix()},
        ) from exc
    except OSError as exc:
        raise MissingHandoffError(
            f"Unable to read handoff checkpoint '{resolved.as_posix()}': {exc}",
            details={"path": resolved.as_posix()},
        ) from exc

    checkpoint = parse_handoff(raw_content, max_bytes=max_bytes)
    return resolved, raw_content, checkpoint


# ---------------------------------------------------------------------------
# Checkpoint Creation
# ---------------------------------------------------------------------------


def create_handoff(
    *,
    objective: str,
    next_action: str,
    completed_work: str | list[str] | None = None,
    decisions: str | list[str] | None = None,
    constraints: str | list[str] | None = None,
    changed_files: str | list[str] | None = None,
    verification: Optional[list[str | dict[str, Any] | VerificationRecord]] = None,
    verification_status: Optional[str] = None,
    blockers: str | list[str] | None = None,
    cwd: Optional[Path | str] = None,
    output_path: Optional[Path | str] = None,
    state_dir: Optional[Path | str] = None,
    slug: Optional[str] = None,
    transcript_path: Optional[str] = None,
    detect_transcript: bool = True,
    claude_home: Optional[Path] = None,
    home: Optional[Path] = None,
    max_bytes: int = DEFAULT_MAX_HANDOFF_BYTES,
    max_section_chars: Optional[int] = None,
    generated_at: Optional[str] = None,
) -> dict[str, Any]:
    """Create, redact, validate, and atomically write a session handoff checkpoint."""
    if not objective or not str(objective).strip():
        raise MalformedHandoffError("Handoff 'objective' is required and must be non-empty.")
    if not next_action or not str(next_action).strip():
        raise MalformedHandoffError("Handoff 'next_action' is required and must be non-empty.")

    git_state = inspect_git_state(
        cwd=cwd,
        transcript_path=transcript_path,
        detect_transcript=detect_transcript,
        claude_home=claude_home,
        home=home,
    )

    timestamp_iso = generated_at or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    raw_objective = _format_bullet_section(objective, "No objective provided.")
    raw_completed = _format_bullet_section(
        completed_work, "No completed work items recorded yet."
    )
    raw_decisions = _format_bullet_section(
        decisions, "No special architectural decisions recorded."
    )
    raw_constraints = _format_bullet_section(
        constraints,
        "Preserve unrelated working-tree changes; treat session transcript as fallback only.",
    )
    raw_changed = _format_changed_files_section(
        git_state.changed_files,
        extra_changed_files=changed_files,
        head_sha=git_state.head_sha,
    )
    v_status, raw_verification = build_verification_section(
        verification_items=verification,
        requested_status=verification_status,
    )
    raw_blockers = _format_bullet_section(blockers, "None.")
    raw_next_action = _format_bullet_section(next_action, "No next action specified.")

    # Apply conservative secret redaction across all text sections
    redaction_total = 0

    def _clean(section_text: str) -> str:
        nonlocal redaction_total
        redacted, n = redact_secrets(section_text)
        redaction_total += n
        return redacted

    clean_objective = _clean(raw_objective)
    clean_completed = _clean(raw_completed)
    clean_decisions = _clean(raw_decisions)
    clean_constraints = _clean(raw_constraints)
    clean_changed = _clean(raw_changed)
    clean_verification = _clean(raw_verification)
    clean_blockers = _clean(raw_blockers)
    clean_next_action = _clean(raw_next_action)

    checkpoint = HandoffCheckpoint(
        schema=SCHEMA_NAME,
        schema_version=SCHEMA_VERSION,
        generated_at=timestamp_iso,
        repo_id=git_state.repo_id,
        repo_root=git_state.repo_root,
        worktree_id=git_state.worktree_id,
        worktree_path=git_state.worktree_path,
        is_linked_worktree=git_state.is_linked_worktree,
        branch=git_state.branch,
        detached=git_state.detached,
        head_sha=git_state.head_sha,
        dirty_state=git_state.dirty_state,
        is_dirty=git_state.is_dirty,
        staged_count=git_state.staged_count,
        unstaged_count=git_state.unstaged_count,
        untracked_count=git_state.untracked_count,
        dirty_entries_hash=git_state.dirty_entries_hash,
        verification_status=v_status,
        transcript_path=git_state.transcript_path,
        transcript_policy=TRANSCRIPT_POLICY,
        size_budget_bytes=max_bytes,
        objective=clean_objective,
        completed_work=clean_completed,
        decisions=clean_decisions,
        constraints=clean_constraints,
        changed_files=clean_changed,
        verification=clean_verification,
        blockers=clean_blockers,
        next_action=clean_next_action,
    )

    rendered = render_handoff(
        checkpoint,
        max_bytes=max_bytes,
        max_section_chars=max_section_chars,
    )
    encoded_bytes = len(rendered.encode("utf-8"))

    worktree_store = get_worktree_store_dir(git_state, state_dir=state_dir, home=home)
    latest_path: Optional[Path] = None

    if output_path is not None and str(output_path).strip():
        target_file = normalize_path(output_path, base_dir=git_state.worktree_path, home=home)
        saved_file = atomic_write_text(target_file, rendered)
        # If the explicit output path is inside our worktree store dir, also update latest.md
        if saved_file.parent == worktree_store and saved_file.name != "latest.md":
            latest_path = atomic_write_text(worktree_store / "latest.md", rendered)
    else:
        ensure_private_dir(worktree_store)
        compact_ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        file_slug = slugify(slug or objective)
        filename = f"{compact_ts}-{file_slug}.md"
        target_file = worktree_store / filename
        counter = 1
        while target_file.exists():
            counter += 1
            target_file = worktree_store / f"{compact_ts}-{counter}-{file_slug}.md"

        saved_file = atomic_write_text(target_file, rendered)
        latest_path = atomic_write_text(worktree_store / "latest.md", rendered)

    return {
        "status": "ok",
        "saved_path": saved_file.as_posix(),
        "latest_path": latest_path.as_posix() if latest_path else None,
        "size_bytes": encoded_bytes,
        "size_budget_bytes": max_bytes,
        "redactions_applied": redaction_total,
        "checkpoint": checkpoint,
        "content": rendered,
    }


# ---------------------------------------------------------------------------
# Listing, Latest Resolution, and Resume Drift Analysis
# ---------------------------------------------------------------------------


def list_handoffs(
    *,
    cwd: Optional[Path | str] = None,
    state_dir: Optional[Path | str] = None,
    home: Optional[Path] = None,
    max_bytes: int = DEFAULT_MAX_HANDOFF_BYTES,
) -> list[dict[str, Any]]:
    """List valid checkpoints for the current repository AND worktree (newest first)."""
    git_state = inspect_git_state(cwd=cwd, detect_transcript=False, home=home)
    worktree_store = get_worktree_store_dir(git_state, state_dir=state_dir, home=home)
    root_store = get_default_state_dir(state_dir=state_dir, home=home)

    candidate_files: list[Path] = []
    seen_paths: set[str] = set()

    def _collect_from_dir(directory: Path, include_latest_fallback: bool = False) -> None:
        if not directory.is_dir():
            return
        md_files = sorted(directory.glob("*.md"))
        non_latest = [p for p in md_files if p.name != "latest.md" and p.is_file()]
        selected = non_latest
        if not selected and include_latest_fallback:
            latest_candidate = directory / "latest.md"
            if latest_candidate.is_file():
                selected = [latest_candidate]
        for path in selected:
            norm = path.resolve(strict=False).as_posix()
            if norm not in seen_paths:
                seen_paths.add(norm)
                candidate_files.append(path)

    _collect_from_dir(worktree_store, include_latest_fallback=True)
    # Also scan flat files in repo_dir or root_store if someone stored checkpoints there,
    # while strictly filtering by repo_id AND worktree_path below.
    _collect_from_dir(root_store / git_state.repo_id, include_latest_fallback=False)
    _collect_from_dir(root_store, include_latest_fallback=False)

    matched: list[tuple[tuple[str, int, str], dict[str, Any]]] = []
    for file_path in candidate_files:
        try:
            resolved_path, _, ckpt = load_handoff_file(
                file_path, max_bytes=max_bytes, home=home
            )
        except HandoffError:
            continue

        # Strictly enforce that both repo_id AND worktree_path match current worktree!
        if ckpt.repo_id != git_state.repo_id:
            continue
        if normalize_path_str(ckpt.worktree_path, home=home) != git_state.worktree_path:
            continue

        try:
            mtime_ns = resolved_path.stat().st_mtime_ns
        except OSError:
            mtime_ns = 0

        sort_key = (ckpt.generated_at, mtime_ns, resolved_path.name)
        matched.append(
            (
                sort_key,
                {
                    "path": resolved_path.as_posix(),
                    "generated_at": ckpt.generated_at,
                    "repo_id": ckpt.repo_id,
                    "worktree_path": ckpt.worktree_path,
                    "branch": ckpt.branch,
                    "detached": ckpt.detached,
                    "head_sha": ckpt.head_sha,
                    "dirty_state": ckpt.dirty_state,
                    "verification_status": ckpt.verification_status,
                    "objective": ckpt.objective,
                    "next_action": ckpt.next_action,
                },
            )
        )

    matched.sort(key=lambda item: item[0], reverse=True)
    return [item[1] for item in matched]


def resolve_latest_handoff(
    *,
    cwd: Optional[Path | str] = None,
    state_dir: Optional[Path | str] = None,
    home: Optional[Path] = None,
    max_bytes: int = DEFAULT_MAX_HANDOFF_BYTES,
) -> Path:
    """Resolve the newest checkpoint for the current repository and worktree."""
    git_state = inspect_git_state(cwd=cwd, detect_transcript=False, home=home)
    worktree_store = get_worktree_store_dir(git_state, state_dir=state_dir, home=home)

    entries = list_handoffs(
        cwd=git_state.worktree_path,
        state_dir=state_dir,
        home=home,
        max_bytes=max_bytes,
    )
    if entries:
        return Path(entries[0]["path"])

    # If the worktree store directory has files that failed validation (e.g. malformed/oversized/wrong_repo),
    # surface that specific validation error when resolving latest so errors are never masked.
    if worktree_store.is_dir():
        raw_candidates = sorted(
            [p for p in worktree_store.glob("*.md") if p.is_file()],
            key=lambda p: p.stat().st_mtime_ns if p.exists() else 0,
            reverse=True,
        )
        for candidate in raw_candidates:
            resolved_path, _, ckpt = load_handoff_file(
                candidate, max_bytes=max_bytes, home=home
            )
            if ckpt.repo_id != git_state.repo_id:
                raise WrongRepositoryError(
                    f"Latest checkpoint in '{resolved_path.as_posix()}' belongs to repository "
                    f"'{ckpt.repo_id}', not current repository '{git_state.repo_id}'.",
                    details={
                        "checkpoint_path": resolved_path.as_posix(),
                        "recorded_repo_id": ckpt.repo_id,
                        "current_repo_id": git_state.repo_id,
                    },
                )

    raise MissingHandoffError(
        f"No handoff checkpoint found for repository '{git_state.repo_id}' "
        f"and worktree '{git_state.worktree_path}' (looked in {worktree_store.as_posix()}).",
        details={
            "repo_id": git_state.repo_id,
            "worktree_path": git_state.worktree_path,
            "expected_store_dir": worktree_store.as_posix(),
        },
    )


def compare_git_drift(
    checkpoint: HandoffCheckpoint,
    current_git: GitState,
    *,
    home: Optional[Path] = None,
) -> list[DriftWarning]:
    """Compare recorded checkpoint state with current Git state and return drift warnings."""
    warnings: list[DriftWarning] = []

    recorded_wt = normalize_path_str(checkpoint.worktree_path, home=home)
    current_wt = normalize_path_str(current_git.worktree_path, home=home)
    if recorded_wt != current_wt:
        warnings.append(
            DriftWarning(
                kind="worktree",
                recorded=recorded_wt,
                current=current_wt,
                message=(
                    f"Worktree drift: checkpoint was created in '{recorded_wt}' "
                    f"but current worktree is '{current_wt}'."
                ),
            )
        )

    recorded_branch_desc = (
        "DETACHED HEAD"
        if checkpoint.detached
        else f"branch '{checkpoint.branch}'"
    )
    current_branch_desc = (
        "DETACHED HEAD"
        if current_git.detached
        else f"branch '{current_git.branch}'"
    )
    if (checkpoint.detached != current_git.detached) or (
        not checkpoint.detached and checkpoint.branch != current_git.branch
    ):
        warnings.append(
            DriftWarning(
                kind="branch",
                recorded="DETACHED" if checkpoint.detached else (checkpoint.branch or ""),
                current="DETACHED" if current_git.detached else (current_git.branch or ""),
                message=(
                    f"Branch drift: checkpoint recorded {recorded_branch_desc} "
                    f"but current Git state is {current_branch_desc}."
                ),
            )
        )

    if checkpoint.head_sha != current_git.head_sha:
        warnings.append(
            DriftWarning(
                kind="head",
                recorded=checkpoint.head_sha,
                current=current_git.head_sha,
                message=(
                    f"HEAD drift: checkpoint recorded commit '{checkpoint.head_sha}' "
                    f"but current HEAD is '{current_git.head_sha}'."
                ),
            )
        )

    dirty_mismatch = (
        checkpoint.is_dirty != current_git.is_dirty
        or checkpoint.staged_count != current_git.staged_count
        or checkpoint.unstaged_count != current_git.unstaged_count
        or checkpoint.untracked_count != current_git.untracked_count
        or checkpoint.dirty_entries_hash != current_git.dirty_entries_hash
        or checkpoint.dirty_state != current_git.dirty_state
    )
    if dirty_mismatch:
        warnings.append(
            DriftWarning(
                kind="dirty_state",
                recorded=checkpoint.dirty_state,
                current=current_git.dirty_state,
                message=(
                    f"Dirty-state drift: checkpoint recorded '{checkpoint.dirty_state}' "
                    f"(hash {checkpoint.dirty_entries_hash}) but current working tree is "
                    f"'{current_git.dirty_state}' (hash {current_git.dirty_entries_hash})."
                ),
            )
        )

    return warnings


def resume_handoff(
    target: Optional[str] = "latest",
    *,
    cwd: Optional[Path | str] = None,
    state_dir: Optional[Path | str] = None,
    home: Optional[Path] = None,
    max_bytes: int = DEFAULT_MAX_HANDOFF_BYTES,
) -> ResumeReport:
    """Resolve, validate, and compare a checkpoint without mutating repository state."""
    current_git = inspect_git_state(cwd=cwd, detect_transcript=False, home=home)

    cleaned_target = (target or "latest").strip()
    if cleaned_target.lower() == "latest":
        checkpoint_path = resolve_latest_handoff(
            cwd=current_git.worktree_path,
            state_dir=state_dir,
            home=home,
            max_bytes=max_bytes,
        )
    else:
        checkpoint_path = normalize_path(
            cleaned_target, base_dir=current_git.worktree_path, home=home
        )

    resolved_path, raw_content, checkpoint = load_handoff_file(
        checkpoint_path,
        max_bytes=max_bytes,
        base_dir=current_git.worktree_path,
        home=home,
    )

    if checkpoint.repo_id != current_git.repo_id:
        raise WrongRepositoryError(
            f"Checkpoint repository mismatch: artifact belongs to '{checkpoint.repo_id}' "
            f"(root '{checkpoint.repo_root}'), but current repository is "
            f"'{current_git.repo_id}' (root '{current_git.repo_root}').",
            details={
                "checkpoint_path": resolved_path.as_posix(),
                "recorded_repo_id": checkpoint.repo_id,
                "recorded_repo_root": checkpoint.repo_root,
                "current_repo_id": current_git.repo_id,
                "current_repo_root": current_git.repo_root,
            },
        )

    drift_warnings = compare_git_drift(checkpoint, current_git, home=home)
    has_drift = len(drift_warnings) > 0
    safe_match = not has_drift
    match_status = "exact_match" if safe_match else "drift_detected"

    if safe_match:
        summary = (
            "SAFE MATCH: Current Git repository, worktree, branch/HEAD, and "
            "working-tree dirty state match the checkpoint."
        )
    else:
        kinds = ", ".join(w.kind for w in drift_warnings)
        summary = (
            f"DRIFT WARNING: {len(drift_warnings)} difference(s) detected between "
            f"checkpoint and current Git state ({kinds}). Review drift before taking action."
        )

    transcript_notice = (
        f"{TRANSCRIPT_FALLBACK_NOTICE} "
        f"(Recorded fallback transcript: {checkpoint.transcript_path or 'not detected'})"
    )

    return ResumeReport(
        checkpoint_path=resolved_path.as_posix(),
        checkpoint=checkpoint,
        current_git=current_git,
        match_status=match_status,
        safe_match=safe_match,
        has_drift=has_drift,
        drift_warnings=drift_warnings,
        summary=summary,
        exact_next_action=checkpoint.next_action,
        transcript_fallback_notice=transcript_notice,
        content=raw_content,
    )


def format_resume_human(report: ResumeReport) -> str:
    """Render a concise, human- and agent-readable resume summary."""
    lines = [
        f"Loaded Handoff Checkpoint: {report.checkpoint_path}",
        f"Validation Status: {report.match_status.upper()}",
        f"Summary: {report.summary}",
    ]
    if report.drift_warnings:
        lines.append("")
        lines.append("Drift Warnings:")
        for warning in report.drift_warnings:
            lines.append(f"  - [{warning.kind}] {warning.message}")
    lines.extend(
        [
            "",
            "Safety & Context Policy:",
            "  - Repository state was NOT modified during resume.",
            "  - Do NOT automatically edit files, switch/reset branches, restore changes, or run commands without reviewing the next action.",
            f"  - {report.transcript_fallback_notice}",
            "",
            "Exact Next Action:",
            report.exact_next_action,
            "",
            "--- Checkpoint Content ---",
            report.content.rstrip(),
        ]
    )
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# CLI Entrypoint
# ---------------------------------------------------------------------------


def _load_create_spec(args: argparse.Namespace) -> dict[str, Any]:
    """Load optional JSON create payload from `--spec-file` or `--stdin-json`."""
    raw_json = ""
    if getattr(args, "spec_file", None):
        spec_path = Path(args.spec_file).expanduser()
        raw_json = spec_path.read_text(encoding="utf-8")
    elif getattr(args, "stdin_json", False):
        raw_json = sys.stdin.read()

    if not raw_json.strip():
        return {}
    try:
        parsed = json.loads(raw_json)
    except json.JSONDecodeError as exc:
        raise MalformedHandoffError(f"Invalid JSON input payload: {exc}") from exc
    if not isinstance(parsed, dict):
        raise MalformedHandoffError("JSON input payload must be an object.")
    return parsed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Daplug provider-neutral session handoff helper."
    )
    subparsers = parser.add_subparsers(dest="subcommand", required=True)

    # inspect
    p_inspect = subparsers.add_parser(
        "inspect",
        help="Inspect factual Git repository/worktree state and handoff storage paths.",
    )
    p_inspect.add_argument("--cwd", help="Working directory inside the Git repository.")
    p_inspect.add_argument("--state-dir", help="Override Daplug handoff storage root directory.")
    p_inspect.add_argument("--no-transcript", action="store_true", help="Skip transcript path detection.")
    p_inspect.add_argument("--json", action="store_true", help="Output JSON.")

    # create
    p_create = subparsers.add_parser(
        "create",
        help="Create a compact, evidence-backed session handoff checkpoint.",
    )
    p_create.add_argument("--objective", help="Session objective summary.")
    p_create.add_argument("--next-action", help="Exact next action for the resuming session.")
    p_create.add_argument(
        "--completed",
        action="append",
        default=None,
        help="Completed work item (repeatable).",
    )
    p_create.add_argument(
        "--decision",
        action="append",
        default=None,
        help="Decision and rationale item (repeatable).",
    )
    p_create.add_argument(
        "--constraint",
        action="append",
        default=None,
        help="Constraint item (repeatable).",
    )
    p_create.add_argument(
        "--changed-file",
        action="append",
        default=None,
        help="Additional changed-file note merged with factual Git status (repeatable).",
    )
    p_create.add_argument(
        "--verify",
        action="append",
        default=None,
        help="Verification record in format 'command :: status :: evidence' (repeatable).",
    )
    p_create.add_argument(
        "--verification-status",
        choices=list(ALLOWED_VERIFICATION_STATUSES),
        help="Explicit overall verification status (validated against supplied evidence).",
    )
    p_create.add_argument(
        "--blocker",
        action="append",
        default=None,
        help="Blocker or unresolved question (repeatable).",
    )
    p_create.add_argument("--slug", help="Optional filename slug override.")
    p_create.add_argument("--output", help="Explicit output file path override.")
    p_create.add_argument("--state-dir", help="Override Daplug handoff storage root directory.")
    p_create.add_argument("--cwd", help="Working directory inside the Git repository.")
    p_create.add_argument("--transcript-path", help="Explicit fallback session transcript path.")
    p_create.add_argument(
        "--no-transcript",
        action="store_true",
        help="Do not auto-detect or record a session transcript path.",
    )
    p_create.add_argument(
        "--max-bytes",
        type=int,
        default=DEFAULT_MAX_HANDOFF_BYTES,
        help=f"Maximum allowed checkpoint size in bytes (default: {DEFAULT_MAX_HANDOFF_BYTES}).",
    )
    p_create.add_argument("--spec-file", help="Read structured handoff fields from a JSON file.")
    p_create.add_argument(
        "--stdin-json",
        action="store_true",
        help="Read structured handoff fields as JSON from stdin.",
    )
    p_create.add_argument("--json", action="store_true", help="Output JSON.")

    # resume
    p_resume = subparsers.add_parser(
        "resume",
        help="Resolve, validate, and load a handoff checkpoint with Git drift checks.",
    )
    p_resume.add_argument(
        "target",
        nargs="?",
        default="latest",
        help="Checkpoint path or 'latest' (default: latest).",
    )
    p_resume.add_argument("--cwd", help="Working directory inside the Git repository.")
    p_resume.add_argument("--state-dir", help="Override Daplug handoff storage root directory.")
    p_resume.add_argument(
        "--max-bytes",
        type=int,
        default=DEFAULT_MAX_HANDOFF_BYTES,
        help=f"Maximum allowed checkpoint size in bytes (default: {DEFAULT_MAX_HANDOFF_BYTES}).",
    )
    p_resume.add_argument("--json", action="store_true", help="Output JSON.")

    # list
    p_list = subparsers.add_parser(
        "list",
        help="List saved handoff checkpoints for the current repository and worktree.",
    )
    p_list.add_argument("--cwd", help="Working directory inside the Git repository.")
    p_list.add_argument("--state-dir", help="Override Daplug handoff storage root directory.")
    p_list.add_argument(
        "--max-bytes",
        type=int,
        default=DEFAULT_MAX_HANDOFF_BYTES,
        help=f"Maximum allowed checkpoint size in bytes (default: {DEFAULT_MAX_HANDOFF_BYTES}).",
    )
    p_list.add_argument("--json", action="store_true", help="Output JSON.")

    return parser


def main(argv: Optional[list[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        if args.subcommand == "inspect":
            git_state = inspect_git_state(
                cwd=args.cwd,
                detect_transcript=not args.no_transcript,
            )
            store_dir = get_worktree_store_dir(git_state, state_dir=args.state_dir)
            existing = list_handoffs(cwd=git_state.worktree_path, state_dir=args.state_dir)
            payload = {
                "status": "ok",
                **git_state.to_dict(),
                "store_dir": store_dir.as_posix(),
                "latest_checkpoint": existing[0]["path"] if existing else None,
                "checkpoint_count": len(existing),
            }
            if args.json:
                print(json.dumps(payload, indent=2))
            else:
                print(f"Repository ID: {git_state.repo_id}")
                print(f"Repository Root: {git_state.repo_root}")
                print(f"Worktree Path: {git_state.worktree_path}")
                print(f"Linked Worktree: {'yes' if git_state.is_linked_worktree else 'no'}")
                print(
                    f"Branch / State: {'DETACHED HEAD' if git_state.detached else git_state.branch}"
                )
                print(f"HEAD SHA: {git_state.head_sha}")
                print(f"Dirty State: {git_state.dirty_state}")
                print(f"Transcript (Fallback): {git_state.transcript_path or 'not detected'}")
                print(f"Store Directory: {store_dir.as_posix()}")
                print(f"Latest Checkpoint: {payload['latest_checkpoint'] or 'none'}")
            return 0

        if args.subcommand == "create":
            spec = _load_create_spec(args)
            objective = args.objective if args.objective is not None else spec.get("objective", "")
            next_action = (
                args.next_action
                if args.next_action is not None
                else spec.get("next_action", "")
            )
            completed = (
                args.completed
                if args.completed is not None
                else spec.get("completed_work", spec.get("completed"))
            )
            decisions = (
                args.decisions
                if hasattr(args, "decisions") and args.decisions is not None
                else (args.decision if args.decision is not None else spec.get("decisions"))
            )
            constraints = (
                args.constraint
                if args.constraint is not None
                else spec.get("constraints")
            )
            changed_files = (
                args.changed_file
                if args.changed_file is not None
                else spec.get("changed_files")
            )
            verify = (
                args.verify
                if args.verify is not None
                else spec.get("verification")
            )
            verification_status = (
                args.verification_status
                if args.verification_status is not None
                else spec.get("verification_status")
            )
            blockers = (
                args.blocker
                if args.blocker is not None
                else spec.get("blockers")
            )
            slug = args.slug if args.slug is not None else spec.get("slug")
            output_path = args.output if args.output is not None else spec.get("output")
            transcript_path = (
                args.transcript_path
                if args.transcript_path is not None
                else spec.get("transcript_path")
            )

            result = create_handoff(
                objective=objective,
                next_action=next_action,
                completed_work=completed,
                decisions=decisions,
                constraints=constraints,
                changed_files=changed_files,
                verification=verify,
                verification_status=verification_status,
                blockers=blockers,
                cwd=args.cwd,
                output_path=output_path,
                state_dir=args.state_dir,
                slug=slug,
                transcript_path=transcript_path,
                detect_transcript=not args.no_transcript,
                max_bytes=args.max_bytes,
            )
            if args.json:
                json_out = {
                    "status": result["status"],
                    "saved_path": result["saved_path"],
                    "latest_path": result["latest_path"],
                    "size_bytes": result["size_bytes"],
                    "size_budget_bytes": result["size_budget_bytes"],
                    "redactions_applied": result["redactions_applied"],
                    "metadata": result["checkpoint"].metadata_dict(),
                }
                print(json.dumps(json_out, indent=2))
            else:
                print(f"Saved handoff checkpoint: {result['saved_path']}")
                if result["latest_path"]:
                    print(f"Updated latest pointer: {result['latest_path']}")
                print(
                    f"Size: {result['size_bytes']} / {result['size_budget_bytes']} bytes "
                    f"(verification: {result['checkpoint'].verification_status}, "
                    f"redactions: {result['redactions_applied']})"
                )
            return 0

        if args.subcommand == "resume":
            report = resume_handoff(
                args.target,
                cwd=args.cwd,
                state_dir=args.state_dir,
                max_bytes=args.max_bytes,
            )
            if args.json:
                print(json.dumps(report.to_dict(), indent=2))
            else:
                print(format_resume_human(report), end="")
            return 0

        if args.subcommand == "list":
            items = list_handoffs(
                cwd=args.cwd,
                state_dir=args.state_dir,
                max_bytes=args.max_bytes,
            )
            if args.json:
                print(json.dumps({"status": "ok", "handoffs": items}, indent=2))
            else:
                if not items:
                    print("No handoff checkpoints found for current repository/worktree.")
                else:
                    for item in items:
                        branch_label = "DETACHED" if item["detached"] else item["branch"]
                        print(
                            f"{item['generated_at']}  {item['head_sha'][:12]}  "
                            f"[{branch_label}]  {item['path']}"
                        )
            return 0

        return 1
    except HandoffError as exc:
        if getattr(args, "json", False):
            print(json.dumps(exc.to_dict(), indent=2))
        else:
            print(f"Error [{exc.error_code}]: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
