#!/usr/bin/env python3
"""Focused unit and integration tests for Daplug's provider-neutral session handoff skill."""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys

import pytest

SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import handoff  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[3]


def _git(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(cwd), *args],
        capture_output=True,
        text=True,
        check=True,
    )


def _init_git_repo(path: Path, branch: str = "main") -> Path:
    path.mkdir(parents=True, exist_ok=True)
    _git(path, "init", "-b", branch)
    _git(path, "config", "user.name", "Daplug Test")
    _git(path, "config", "user.email", "test@example.invalid")
    readme = path / "README.md"
    readme.write_text("# Test Repo\n", encoding="utf-8")
    _git(path, "add", "README.md")
    _git(path, "commit", "-m", "initial commit")
    return path


# ---------------------------------------------------------------------------
# 1. Creation, Schema Round-Trip, Atomic Replacement, Permissions, Identity
# ---------------------------------------------------------------------------


def test_create_roundtrip_permissions_and_untracked_storage(tmp_path: Path):
    repo = _init_git_repo(tmp_path / "repo")
    state_dir = tmp_path / "state"
    fake_home = tmp_path / "home"

    # Simulate a Claude session transcript to verify detection & fallback policy
    claude_projects = fake_home / ".claude" / "projects"
    slug = re.sub(r"[^a-zA-Z0-9]", "-", str(repo.resolve()))
    sess_dir = claude_projects / slug
    sess_dir.mkdir(parents=True)
    transcript_file = sess_dir / "session-001.jsonl"
    transcript_file.write_text('{"event":"never_read_me"}\n', encoding="utf-8")

    result = handoff.create_handoff(
        objective="Implement provider-neutral session handoff",
        completed_work=["Created handoff.py", "Added schema parser and renderer"],
        decisions=["Use YAML frontmatter with JSON-encoded scalars for stdlib round-trip"],
        constraints=["Do not pollute git status or edit .gitignore"],
        verification=[
            "python3 -m pytest skills/handoff/tests -v :: passed :: 14 passed in 0.22s (exit 0)"
        ],
        blockers=["None."],
        next_action="Run ./scripts/run-tests.sh and verify all suites pass.",
        cwd=repo,
        state_dir=state_dir,
        home=fake_home,
        generated_at="2026-10-19T19:30:00Z",
    )

    saved_path = Path(result["saved_path"])
    latest_path = Path(result["latest_path"])
    assert saved_path.is_file()
    assert latest_path.is_file()

    # Storage must be outside repo working tree and leave git status completely clean
    assert not saved_path.is_relative_to(repo)
    status_out = _git(repo, "status", "--porcelain=v1", "-uall").stdout
    assert status_out == ""

    # File and directory permissions must be restrictive (0600 file, 0700 dir)
    assert stat.S_IMODE(saved_path.stat().st_mode) == 0o600
    assert stat.S_IMODE(latest_path.stat().st_mode) == 0o600
    assert stat.S_IMODE(saved_path.parent.stat().st_mode) == 0o700

    # Schema round-trip must be lossless
    raw_markdown = saved_path.read_text(encoding="utf-8")
    parsed = handoff.parse_handoff(raw_markdown)
    assert parsed.to_dict() == result["checkpoint"].to_dict()
    assert handoff.render_handoff(parsed) == raw_markdown

    # Metadata & fallback transcript checks
    assert parsed.schema == "daplug-handoff"
    assert parsed.schema_version == 1
    assert parsed.branch == "main"
    assert parsed.detached is False
    assert len(parsed.head_sha) == 40
    assert parsed.is_dirty is False
    assert parsed.verification_status == "passed"
    assert parsed.transcript_path == transcript_file.resolve().as_posix()
    assert parsed.transcript_policy == "fallback_only_do_not_read_by_default"
    assert "FALLBACK ONLY" in raw_markdown
    assert "Do NOT read or replay the full session transcript" in raw_markdown


def test_atomic_replacement_preserves_target_and_leaves_no_tmp_files(tmp_path: Path, monkeypatch):
    target = tmp_path / "handoffs" / "checkpoint.md"
    handoff.atomic_write_text(target, "first version\n")
    assert target.read_text(encoding="utf-8") == "first version\n"
    assert stat.S_IMODE(target.stat().st_mode) == 0o600

    # Replace atomically with new content
    os.chmod(target, 0o644)
    handoff.atomic_write_text(target, "second version\n")
    assert target.read_text(encoding="utf-8") == "second version\n"
    assert stat.S_IMODE(target.stat().st_mode) == 0o600
    assert list(target.parent.glob("*.tmp")) == []

    # Simulate failure before os.replace: original file must remain intact and temp file cleaned up
    real_replace = os.replace

    def _failing_replace(src, dst):
        raise OSError("simulated atomic replace failure")

    monkeypatch.setattr(os, "replace", _failing_replace)
    with pytest.raises(OSError, match="simulated atomic replace failure"):
        handoff.atomic_write_text(target, "corrupted third version\n")

    monkeypatch.setattr(os, "replace", real_replace)
    assert target.read_text(encoding="utf-8") == "second version\n"
    assert list(target.parent.glob("*.tmp")) == []


def test_deterministic_repo_identity_across_subdirectories_and_worktrees(tmp_path: Path):
    repo_a = _init_git_repo(tmp_path / "org-a" / "service")
    repo_b = _init_git_repo(tmp_path / "org-b" / "service")
    subdir_a = repo_a / "nested" / "pkg"
    subdir_a.mkdir(parents=True)

    linked_wt = tmp_path / "worktrees" / "service-feature"
    _git(repo_a, "worktree", "add", "-b", "feature/wt", str(linked_wt), "main")

    state_root_1 = handoff.inspect_git_state(cwd=repo_a, detect_transcript=False)
    state_root_2 = handoff.inspect_git_state(cwd=repo_a, detect_transcript=False)
    state_sub = handoff.inspect_git_state(cwd=subdir_a, detect_transcript=False)
    state_wt = handoff.inspect_git_state(cwd=linked_wt, detect_transcript=False)
    state_other = handoff.inspect_git_state(cwd=repo_b, detect_transcript=False)

    # Same repo -> identical repo_id even from subdirectories or linked worktrees
    assert state_root_1.repo_id == state_root_2.repo_id
    assert state_root_1.repo_id == state_sub.repo_id
    assert state_root_1.repo_id == state_wt.repo_id

    # Worktree IDs differ between main checkout and linked worktree
    assert state_root_1.worktree_id == state_sub.worktree_id
    assert state_root_1.worktree_id != state_wt.worktree_id
    assert state_root_1.is_linked_worktree is False
    assert state_wt.is_linked_worktree is True

    # Different repo with the exact same directory name ("service") has a distinct repo_id
    assert state_root_1.repo_id != state_other.repo_id


# ---------------------------------------------------------------------------
# 2. Git Topologies: Detached HEAD, Dirty Tree, Linked Worktree, Missing Repo, Spaces
# ---------------------------------------------------------------------------


def test_detached_head_and_dirty_tree_and_paths_with_spaces(tmp_path: Path):
    repo = _init_git_repo(tmp_path / "dir with spaces" / "my repo name")
    state_dir = tmp_path / "state with spaces"

    # Detach HEAD at current commit
    head_sha = _git(repo, "rev-parse", "HEAD").stdout.strip()
    _git(repo, "checkout", "--detach", head_sha)

    # Create staged, unstaged, and untracked files including spaces in paths
    staged_file = repo / "folder with spaces" / "staged file.py"
    staged_file.parent.mkdir(parents=True)
    staged_file.write_text("print('staged')\n", encoding="utf-8")
    _git(repo, "add", str(staged_file))

    # Modify tracked README.md (unstaged)
    (repo / "README.md").write_text("# Modified Readme\n", encoding="utf-8")

    # Add untracked file with spaces
    untracked_file = repo / "folder with spaces" / "untracked notes.txt"
    untracked_file.write_text("untracked\n", encoding="utf-8")

    res = handoff.create_handoff(
        objective="Test detached HEAD and spaces in paths",
        next_action="Inspect changed files and commit when ready.",
        cwd=repo,
        state_dir=state_dir,
        detect_transcript=False,
    )

    ckpt: handoff.HandoffCheckpoint = res["checkpoint"]
    assert ckpt.detached is True
    assert ckpt.branch is None
    assert ckpt.head_sha == head_sha
    assert ckpt.is_dirty is True
    assert ckpt.staged_count == 1
    assert ckpt.unstaged_count == 1
    assert ckpt.untracked_count == 1
    assert "dirty (1 staged, 1 unstaged, 1 untracked)" == ckpt.dirty_state
    assert "folder with spaces/staged file.py" in ckpt.changed_files
    assert "folder with spaces/untracked notes.txt" in ckpt.changed_files
    assert "README.md" in ckpt.changed_files

    # Round-trip resume in the same detached dirty repo with spaces
    report = handoff.resume_handoff("latest", cwd=repo, state_dir=state_dir)
    assert report.safe_match is True
    assert report.match_status == "exact_match"
    assert report.drift_warnings == []


def test_missing_git_repository_rejected_cleanly(tmp_path: Path):
    non_repo = tmp_path / "not-a-git-repo"
    non_repo.mkdir()

    with pytest.raises(handoff.NotAGitRepositoryError) as exc_info:
        handoff.inspect_git_state(cwd=non_repo, detect_transcript=False)
    assert exc_info.value.error_code == "not_git_repo"

    rc = handoff.main(
        [
            "create",
            "--cwd",
            str(non_repo),
            "--objective",
            "Fail outside git",
            "--next-action",
            "Initialize git first",
            "--json",
        ]
    )
    assert rc == 1


# ---------------------------------------------------------------------------
# 3. Scoped `latest` Resolution Across Repositories and Linked Worktrees
# ---------------------------------------------------------------------------


def test_latest_selection_isolated_across_repositories_and_linked_worktrees(tmp_path: Path):
    state_dir = tmp_path / "shared-state"
    repo_1 = _init_git_repo(tmp_path / "repo-one")
    repo_2 = _init_git_repo(tmp_path / "repo-two")
    linked_wt = tmp_path / "worktrees" / "repo-one-wt"
    _git(repo_1, "worktree", "add", "-b", "wt-branch", str(linked_wt), "main")

    # Create checkpoint in repo_1 main worktree
    r1 = handoff.create_handoff(
        objective="Repo 1 main worktree objective",
        next_action="Action for repo 1 main worktree",
        cwd=repo_1,
        state_dir=state_dir,
        detect_transcript=False,
        generated_at="2026-10-19T10:00:00Z",
    )

    # Linked worktree of repo_1 must NOT consume repo_1 main worktree's `latest`
    with pytest.raises(handoff.MissingHandoffError):
        handoff.resume_handoff("latest", cwd=linked_wt, state_dir=state_dir)

    # Repo 2 must NOT consume repo_1's `latest`
    with pytest.raises(handoff.MissingHandoffError):
        handoff.resume_handoff("latest", cwd=repo_2, state_dir=state_dir)

    # Create checkpoint in linked_wt and newer checkpoint in repo_2
    r_wt = handoff.create_handoff(
        objective="Repo 1 linked worktree objective",
        next_action="Action for linked worktree",
        cwd=linked_wt,
        state_dir=state_dir,
        detect_transcript=False,
        generated_at="2026-10-19T11:00:00Z",
    )
    r2 = handoff.create_handoff(
        objective="Repo 2 objective",
        next_action="Action for repo 2",
        cwd=repo_2,
        state_dir=state_dir,
        detect_transcript=False,
        generated_at="2026-10-19T12:00:00Z",
    )

    # Each checkout resolves strictly its own `latest` checkpoint
    res_1 = handoff.resume_handoff("latest", cwd=repo_1, state_dir=state_dir)
    res_wt = handoff.resume_handoff("latest", cwd=linked_wt, state_dir=state_dir)
    res_2 = handoff.resume_handoff("latest", cwd=repo_2, state_dir=state_dir)

    assert res_1.checkpoint_path == r1["saved_path"]
    assert "Action for repo 1 main worktree" in res_1.exact_next_action

    assert res_wt.checkpoint_path == r_wt["saved_path"]
    assert "Action for linked worktree" in res_wt.exact_next_action

    assert res_2.checkpoint_path == r2["saved_path"]
    assert "Action for repo 2" in res_2.exact_next_action


# ---------------------------------------------------------------------------
# 4. Exact-Match Resume + Branch/HEAD/Worktree/Dirty-State Drift Warnings
# ---------------------------------------------------------------------------


def test_resume_exact_match_and_drift_warnings_without_mutating_repo(tmp_path: Path):
    state_dir = tmp_path / "state"
    repo = _init_git_repo(tmp_path / "repo")
    linked_wt = tmp_path / "worktrees" / "linked"
    _git(repo, "worktree", "add", "-b", "feature/linked", str(linked_wt), "main")

    # Create initial checkpoint in main repo
    created = handoff.create_handoff(
        objective="Initial clean state on main",
        next_action="Continue implementation on main",
        cwd=repo,
        state_dir=state_dir,
        detect_transcript=False,
    )
    ckpt_path = created["saved_path"]

    # 1) Exact match
    exact = handoff.resume_handoff(ckpt_path, cwd=repo, state_dir=state_dir)
    assert exact.safe_match is True
    assert exact.match_status == "exact_match"
    assert exact.drift_warnings == []

    # 2) Dirty-state drift (introduce untracked file)
    untracked = repo / "scratch.txt"
    untracked.write_text("dirty change\n", encoding="utf-8")
    dirty_report = handoff.resume_handoff("latest", cwd=repo, state_dir=state_dir)
    assert dirty_report.safe_match is False
    assert dirty_report.match_status == "drift_detected"
    assert [w.kind for w in dirty_report.drift_warnings] == ["dirty_state"]
    # Verify resume did not remove or touch the dirty file
    assert untracked.read_text(encoding="utf-8") == "dirty change\n"

    # 3) Branch + HEAD + dirty_state drift
    _git(repo, "checkout", "-b", "feature/drifted")
    _git(repo, "add", "scratch.txt")
    _git(repo, "commit", "-m", "commit on drifted branch")
    (repo / "README.md").write_text("unstaged edit\n", encoding="utf-8")

    branch_head_report = handoff.resume_handoff("latest", cwd=repo, state_dir=state_dir)
    drift_kinds = {w.kind for w in branch_head_report.drift_warnings}
    assert drift_kinds == {"branch", "head", "dirty_state"}

    # Verify resume did NOT switch branches, reset commits, or restore files
    assert _git(repo, "symbolic-ref", "--short", "HEAD").stdout.strip() == "feature/drifted"
    assert (repo / "README.md").read_text(encoding="utf-8") == "unstaged edit\n"

    # 4) Worktree drift (resuming main worktree's explicit checkpoint from linked_wt of same repo)
    wt_report = handoff.resume_handoff(ckpt_path, cwd=linked_wt, state_dir=state_dir)
    wt_drift_kinds = {w.kind for w in wt_report.drift_warnings}
    assert "worktree" in wt_drift_kinds
    assert "branch" in wt_drift_kinds


# ---------------------------------------------------------------------------
# 5. Error Handling: Missing, Malformed, Unsupported Version, Oversized, Wrong Repo
# ---------------------------------------------------------------------------


def test_missing_malformed_unsupported_oversized_and_wrong_repo_artifacts(tmp_path: Path):
    state_dir = tmp_path / "state"
    repo_a = _init_git_repo(tmp_path / "repo-a")
    repo_b = _init_git_repo(tmp_path / "repo-b")

    # 5a) Missing artifact
    with pytest.raises(handoff.MissingHandoffError) as exc_missing:
        handoff.resume_handoff(str(tmp_path / "nonexistent.md"), cwd=repo_a, state_dir=state_dir)
    assert exc_missing.value.error_code == "missing"

    # 5b) Malformed artifacts (no frontmatter, missing section)
    malformed_no_fm = tmp_path / "malformed-no-fm.md"
    malformed_no_fm.write_text("# Not a handoff file\n", encoding="utf-8")
    with pytest.raises(handoff.MalformedHandoffError) as exc_mal1:
        handoff.resume_handoff(str(malformed_no_fm), cwd=repo_a, state_dir=state_dir)
    assert exc_mal1.value.error_code == "malformed"

    valid = handoff.create_handoff(
        objective="Valid checkpoint",
        next_action="Valid next action",
        cwd=repo_a,
        state_dir=state_dir,
        detect_transcript=False,
    )
    valid_text = Path(valid["saved_path"]).read_text(encoding="utf-8")

    # Remove '## Exact Next Action' section to trigger missing-section malformed error
    missing_sec_text = valid_text.split("## Exact Next Action")[0]
    malformed_sec = tmp_path / "malformed-missing-section.md"
    malformed_sec.write_text(missing_sec_text, encoding="utf-8")
    with pytest.raises(handoff.MalformedHandoffError) as exc_mal2:
        handoff.resume_handoff(str(malformed_sec), cwd=repo_a, state_dir=state_dir)
    assert exc_mal2.value.error_code == "malformed"

    # 5c) Unsupported schema version
    unsupported_text = valid_text.replace("schema_version: 1", "schema_version: 99", 1)
    unsupported_file = tmp_path / "unsupported-version.md"
    unsupported_file.write_text(unsupported_text, encoding="utf-8")
    with pytest.raises(handoff.UnsupportedVersionError) as exc_ver:
        handoff.resume_handoff(str(unsupported_file), cwd=repo_a, state_dir=state_dir)
    assert exc_ver.value.error_code == "unsupported_version"

    # 5d) Oversized artifact on disk
    oversized_file = tmp_path / "oversized.md"
    oversized_file.write_text(valid_text + ("x" * 20000), encoding="utf-8")
    with pytest.raises(handoff.OversizedHandoffError) as exc_over:
        handoff.resume_handoff(str(oversized_file), cwd=repo_a, state_dir=state_dir)
    assert exc_over.value.error_code == "oversized"

    # 5e) Wrong repository artifact
    with pytest.raises(handoff.WrongRepositoryError) as exc_wrong:
        handoff.resume_handoff(valid["saved_path"], cwd=repo_b, state_dir=state_dir)
    assert exc_wrong.value.error_code == "wrong_repository"


# ---------------------------------------------------------------------------
# 6. Size Budget Enforcement, Verification Honesty, and Secret Redaction
# ---------------------------------------------------------------------------


def test_size_budget_and_raw_diff_enforcement_never_silently_truncate(tmp_path: Path):
    repo = _init_git_repo(tmp_path / "repo")
    state_dir = tmp_path / "state"

    # Oversized section exceeds per-section char budget
    huge_objective = "A" * (handoff.DEFAULT_MAX_SECTION_CHARS + 100)
    with pytest.raises(handoff.OversizedHandoffError) as exc_sec:
        handoff.create_handoff(
            objective=huge_objective,
            next_action="Compact objective first",
            cwd=repo,
            state_dir=state_dir,
            detect_transcript=False,
        )
    assert exc_sec.value.error_code == "oversized"

    # Tight total byte budget fails rather than silently truncating sections
    with pytest.raises(handoff.OversizedHandoffError) as exc_total:
        handoff.create_handoff(
            objective="Normal objective text",
            completed_work=["Item " + ("B" * 300)],
            next_action="Normal next action",
            cwd=repo,
            state_dir=state_dir,
            detect_transcript=False,
            max_bytes=500,
        )
    assert exc_total.value.error_code == "oversized"

    # Raw unified diff embedded in section is rejected
    diff_snippet = "diff --git a/foo.py b/foo.py\n--- a/foo.py\n+++ b/foo.py\n@@ -1 +1 @@\n-old\n+new"
    with pytest.raises(handoff.OversizedHandoffError):
        handoff.create_handoff(
            objective="Attempt to embed raw diff",
            completed_work=diff_snippet,
            next_action="Summarize changes instead",
            cwd=repo,
            state_dir=state_dir,
            detect_transcript=False,
        )


def test_verification_honesty_never_claims_passed_without_evidence(tmp_path: Path):
    repo = _init_git_repo(tmp_path / "repo")
    state_dir = tmp_path / "state"

    # Default when omitted is "not run"
    r_default = handoff.create_handoff(
        objective="No tests run yet",
        next_action="Run pytest",
        cwd=repo,
        state_dir=state_dir,
        detect_transcript=False,
    )
    assert r_default["checkpoint"].verification_status == "not run"

    # Requesting verification_status="passed" without evidence downgrades to "unknown"
    r_unverified_status = handoff.create_handoff(
        objective="Unverified status claim",
        next_action="Run pytest with evidence",
        verification_status="passed",
        cwd=repo,
        state_dir=state_dir,
        detect_transcript=False,
    )
    assert r_unverified_status["checkpoint"].verification_status == "unknown"
    assert "downgraded to `unknown`" in r_unverified_status["checkpoint"].verification

    # Passing a bare "passed" record without evidence or free-form "All tests passed" downgrades to "unknown"
    r_bare_claim = handoff.create_handoff(
        objective="Bare pass claim",
        next_action="Provide real test output",
        verification=["pytest :: passed ::", "All unit tests passed"],
        cwd=repo,
        state_dir=state_dir,
        detect_transcript=False,
    )
    assert r_bare_claim["checkpoint"].verification_status == "unknown"
    assert "`[passed]`" not in r_bare_claim["checkpoint"].verification


def test_secret_redaction_removes_credentials_while_preserving_normal_context(tmp_path: Path):
    repo = _init_git_repo(tmp_path / "repo")
    state_dir = tmp_path / "state"

    # Construct synthetic credential strings dynamically so test source never triggers secret scanners
    fake_sk = "sk-" + "proj-" + ("A1b2C3" * 5)
    fake_ghp = "ghp_" + ("9z8Y7x" * 6)
    fake_glpat = "glpat-" + ("QwErTy" * 4)
    fake_aws = "AKIA" + ("ABCD1234EFGH5678")
    fake_slack = "xoxb-" + "1234567890-abcdef123456"
    fake_bearer = "Bearer " + ("eyJhbGciOiJIUzI1NiJ9." + "eyJzdWIiOiIxMjM0NTYifQ." + "SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c")
    fake_url = "https://" + "deploy_user" + ":" + "SuperSecretPw99!" + "@registry.example.com/v2/"
    fake_pem = (
        "-----BEGIN " + "RSA PRIVATE KEY-----\n"
        "MIIEowIBAAKCAQEA0123456789\n"
        "-----END " + "RSA PRIVATE KEY-----"
    )
    fake_kv = "SYNTHETIC_API_KEY=" + "syn_live_9988776655443322"

    res = handoff.create_handoff(
        objective=f"Rotate credentials ({fake_sk}) and verify GitHub integration ({fake_ghp})",
        completed_work=[
            f"Tested GitLab token {fake_glpat} and AWS key {fake_aws}",
            f"Updated Slack notifier {fake_slack} and registry {fake_url}",
        ],
        decisions=[f"Removed inline {fake_kv} and header Authorization: {fake_bearer}"],
        constraints=[f"Never store PEM blocks:\n{fake_pem}"],
        next_action="Run verification suite on commit 0123456789abcdef0123456789abcdef01234567.",
        cwd=repo,
        state_dir=state_dir,
        detect_transcript=False,
    )

    content = res["content"]
    assert res["redactions_applied"] >= 8

    # None of the raw secret values may appear in the rendered checkpoint
    for secret_fragment in (
        fake_sk,
        fake_ghp,
        fake_glpat,
        fake_aws,
        fake_slack,
        "SuperSecretPw99!",
        "MIIEowIBAAKCAQEA0123456789",
        "syn_live_9988776655443322",
        "SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c",
    ):
        assert secret_fragment not in content

    # Redaction markers are present and normal commit SHAs / prose remain intact
    assert "[REDACTED:" in content
    assert "0123456789abcdef0123456789abcdef01234567" in content


# ---------------------------------------------------------------------------
# 7. Command Markdown & Skill Path Resolution Conventions
# ---------------------------------------------------------------------------


def test_command_markdown_and_skill_follow_plugin_conventions():
    handoff_cmd = REPO_ROOT / "commands" / "handoff.md"
    resume_cmd = REPO_ROOT / "commands" / "resume-handoff.md"
    skill_md = REPO_ROOT / "skills" / "handoff" / "SKILL.md"
    helper_py = REPO_ROOT / "skills" / "handoff" / "scripts" / "handoff.py"
    readme_md = REPO_ROOT / "README.md"
    claude_md = REPO_ROOT / "CLAUDE.md"

    assert handoff_cmd.is_file()
    assert resume_cmd.is_file()
    assert skill_md.is_file()
    assert helper_py.is_file()

    manifest_lookup = 'jq -r \'.plugins."daplug@cruzanstx"[0].installPath\' ~/.claude/plugins/installed_plugins.json'
    rel_script_ref = "skills/handoff/scripts/handoff.py"

    for cmd_path, expected_name in (
        (handoff_cmd, "handoff"),
        (resume_cmd, "resume-handoff"),
    ):
        text = cmd_path.read_text(encoding="utf-8")
        assert text.startswith("---\n")
        assert f"name: {expected_name}\n" in text
        assert "description:" in text
        assert "argument-hint:" in text
        assert manifest_lookup in text
        assert rel_script_ref in text
        # Verify ${CLAUDE_PLUGIN_ROOT} is not used as an active command variable
        code_blocks = re.findall(r"```(?:bash|sh)?\n(.*?)```", text, flags=re.DOTALL)
        assert code_blocks, f"Expected bash code blocks in {cmd_path}"
        for block in code_blocks:
            assert "${CLAUDE_PLUGIN_ROOT}" not in block

    readme_text = readme_md.read_text(encoding="utf-8")
    assert "`/daplug:handoff`" in readme_text
    assert "`/daplug:resume-handoff`" in readme_text
    assert "`handoff`" in readme_text

    claude_text = claude_md.read_text(encoding="utf-8")
    assert "`handoff`" in claude_text


def test_cli_inspect_create_list_and_resume_end_to_end(tmp_path: Path, capsys):
    repo = _init_git_repo(tmp_path / "cli-repo")
    state_dir = tmp_path / "cli-state"

    # 1) inspect --json
    assert handoff.main(["inspect", "--cwd", str(repo), "--state-dir", str(state_dir), "--json"]) == 0
    inspect_out = json.loads(capsys.readouterr().out)
    assert inspect_out["status"] == "ok"
    assert inspect_out["checkpoint_count"] == 0

    # 2) create via --spec-file and --json
    spec_file = tmp_path / "spec.json"
    spec_file.write_text(
        json.dumps(
            {
                "objective": "CLI end-to-end test",
                "completed_work": ["Implemented CLI subcommands"],
                "decisions": ["Keep orchestration in Markdown and logic in Python"],
                "constraints": ["Do not mutate repo on resume"],
                "verification": [
                    "pytest -q :: passed :: 5 passed in 0.10s (exit 0)",
                    "flake8 :: not run ::",
                ],
                "blockers": ["None."],
                "next_action": "Run integration check.",
            }
        ),
        encoding="utf-8",
    )
    assert (
        handoff.main(
            [
                "create",
                "--cwd",
                str(repo),
                "--state-dir",
                str(state_dir),
                "--spec-file",
                str(spec_file),
                "--no-transcript",
                "--json",
            ]
        )
        == 0
    )
    create_out = json.loads(capsys.readouterr().out)
    assert create_out["status"] == "ok"
    assert create_out["metadata"]["verification_status"] == "partial"
    saved_path = create_out["saved_path"]

    # 3) list --json
    assert handoff.main(["list", "--cwd", str(repo), "--state-dir", str(state_dir), "--json"]) == 0
    list_out = json.loads(capsys.readouterr().out)
    assert len(list_out["handoffs"]) == 1
    assert list_out["handoffs"][0]["path"] == saved_path

    # 4) resume latest (human output and JSON output)
    assert handoff.main(["resume", "latest", "--cwd", str(repo), "--state-dir", str(state_dir)]) == 0
    human_resume = capsys.readouterr().out
    assert "Validation Status: EXACT_MATCH" in human_resume
    assert "Run integration check." in human_resume

    assert (
        handoff.main(
            ["resume", saved_path, "--cwd", str(repo), "--state-dir", str(state_dir), "--json"]
        )
        == 0
    )
    json_resume = json.loads(capsys.readouterr().out)
    assert json_resume["match_status"] == "exact_match"
    assert json_resume["safe_match"] is True


def test_resume_never_reads_fallback_transcript_and_normalizes_custom_home(tmp_path: Path):
    custom_home = tmp_path / "custom-users" / "alice"
    custom_home.mkdir(parents=True)
    repo = _init_git_repo(custom_home / "projects" / "app")

    # Create a transcript file and then make it unreadable (0000) or replace with a trap
    transcript = custom_home / ".claude" / "projects" / "trap.jsonl"
    transcript.parent.mkdir(parents=True, exist_ok=True)
    transcript.write_text("secret transcript line\n", encoding="utf-8")

    created = handoff.create_handoff(
        objective="Test custom home normalization and transcript isolation",
        next_action="Verify transcript is never read during resume",
        cwd="~/projects/app",
        transcript_path="~/.claude/projects/trap.jsonl",
        home=custom_home,
    )

    # Delete transcript file after creation to prove resume never opens or reads it
    transcript.unlink()

    report = handoff.resume_handoff(
        "latest",
        cwd="~/projects/app",
        home=custom_home,
    )
    assert report.safe_match is True
    assert report.checkpoint.transcript_path == transcript.resolve(strict=False).as_posix()
    assert "FALLBACK ONLY" in report.transcript_fallback_notice

