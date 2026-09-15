import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.append(str(SCRIPT_DIR))

import manager  # noqa: E402


def _prompt(root: Path, number: int, name: str = "test") -> Path:
    path = root / "prompts" / f"{number:03d}-{name}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("test")
    return path


def test_next_number_scans_sibling_worktrees(tmp_path, monkeypatch):
    primary = tmp_path / "primary"
    sibling = tmp_path / "sibling"
    _prompt(primary, 17, "primary")
    _prompt(sibling, 23, "sibling")
    monkeypatch.setattr(manager, "_get_worktree_roots", lambda _root: [primary, sibling])
    monkeypatch.setattr(manager, "_get_git_common_dir", lambda _root: tmp_path / "common")

    assert manager.get_next_number(primary) == "024"


def test_deleted_prompt_number_is_not_reused(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    monkeypatch.setattr(manager, "_get_worktree_roots", lambda _root: [repo])
    monkeypatch.setattr(manager, "_get_git_common_dir", lambda _root: tmp_path / "common")
    prompt = manager.create_prompt("first", "content", repo_root=repo)
    prompt.path.unlink()

    assert manager.get_next_number(repo) == "002"


def test_deleted_explicit_prompt_number_is_not_reused(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    monkeypatch.setattr(manager, "_get_worktree_roots", lambda _root: [repo])
    monkeypatch.setattr(manager, "_get_git_common_dir", lambda _root: tmp_path / "common")
    prompt = manager.create_prompt("manual", "content", number="005", repo_root=repo)
    prompt.path.unlink()

    assert manager.get_next_number(repo) == "006"


def test_live_allocation_lock_is_not_stolen(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    monkeypatch.setattr(manager, "_get_git_common_dir", lambda _root: tmp_path / "common")

    with manager._prompt_number_lock(repo):
        with pytest.raises(TimeoutError):
            with manager._prompt_number_lock(repo, timeout=0.05):
                pass


def test_parallel_creates_allocate_unique_numbers(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    monkeypatch.setattr(manager, "_get_worktree_roots", lambda _root: [repo])
    monkeypatch.setattr(manager, "_get_git_common_dir", lambda _root: tmp_path / "common")

    with ThreadPoolExecutor(max_workers=8) as pool:
        prompts = list(pool.map(lambda index: manager.create_prompt(f"task-{index}", "content", repo_root=repo), range(8)))

    assert sorted(prompt.number for prompt in prompts) == [f"{number:03d}" for number in range(1, 9)]
    assert len({prompt.path for prompt in prompts}) == 8


def test_get_project_slug():
    p = Path("/storage/projects/docker/daplug")
    slug = manager.get_project_slug(p)
    assert slug == "-storage-projects-docker-daplug"

    p2 = Path("/root/obsidian_vault/vault/htb/Machines/4.Insane/Hercules.10.129.242.196")
    slug2 = manager.get_project_slug(p2)
    assert slug2 == "-root-obsidian-vault-vault-htb-Machines-4-Insane-Hercules-10-129-242-196"


def test_format_session_reference():
    session_file = Path("/root/.claude/projects/-storage-projects-docker-daplug/abc-123.jsonl")
    ref = manager.format_session_reference(session_file)
    assert "\n\n---\n**Session Context**: For full conversation context, see: `/root/.claude/projects/-storage-projects-docker-daplug/abc-123.jsonl`" == ref


def test_get_session_file(tmp_path):
    claude_home = tmp_path / ".claude"
    projects_dir = claude_home / "projects"
    projects_dir.mkdir(parents=True)

    project_slug = "-test-project"
    project_dir = projects_dir / project_slug
    project_dir.mkdir()

    # No files yet
    cwd = Path("/test/project")
    assert manager.get_session_file(cwd=cwd, claude_home=claude_home) is None

    # Add older file
    old_file = project_dir / "old-session.jsonl"
    old_file.write_text("old")
    os.utime(old_file, (time.time() - 100, time.time() - 100))

    # Add newer file
    new_file = project_dir / "new-session.jsonl"
    new_file.write_text("new")
    os.utime(new_file, (time.time(), time.time()))

    found = manager.get_session_file(cwd=cwd, claude_home=claude_home)
    assert found == new_file


def test_create_prompt_with_session_ref(tmp_path, monkeypatch):
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    (repo_root / "prompts").mkdir()

    claude_home = tmp_path / ".claude"
    projects_dir = claude_home / "projects"
    projects_dir.mkdir(parents=True)

    slug = manager.get_project_slug(repo_root)
    proj_dir = projects_dir / slug
    proj_dir.mkdir()
    session_file = proj_dir / "test-session.jsonl"
    session_file.write_text("session data")

    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    prompt = manager.create_prompt(
        name="test task",
        content="<objective>Do work</objective>",
        repo_root=repo_root,
        include_session_ref=True,
    )

    content = prompt.path.read_text()
    assert "<objective>Do work</objective>" in content
    assert "**Session Context**: For full conversation context, see:" in content
    assert str(session_file) in content


def test_create_prompt_no_duplicate_session_ref(tmp_path, monkeypatch):
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    (repo_root / "prompts").mkdir()

    claude_home = tmp_path / ".claude"
    projects_dir = claude_home / "projects"
    projects_dir.mkdir(parents=True)

    slug = manager.get_project_slug(repo_root)
    proj_dir = projects_dir / slug
    proj_dir.mkdir()
    session_file = proj_dir / "test-session.jsonl"
    session_file.write_text("session data")

    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    existing_ref_content = "<objective>Do work</objective>\n\n---\n**Session Context**: For full conversation context, see: `/custom/path.jsonl`"
    prompt = manager.create_prompt(
        name="test task 2",
        content=existing_ref_content,
        repo_root=repo_root,
        include_session_ref=True,
    )

    content = prompt.path.read_text()
    assert content.count("**Session Context**") == 1
    assert "/custom/path.jsonl" in content


def test_get_info_with_session_file(tmp_path, monkeypatch):
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    (repo_root / "prompts").mkdir()

    claude_home = tmp_path / ".claude"
    projects_dir = claude_home / "projects"
    projects_dir.mkdir(parents=True)

    slug = manager.get_project_slug(repo_root)
    proj_dir = projects_dir / slug
    proj_dir.mkdir()
    session_file = proj_dir / "my-session.jsonl"
    session_file.write_text("data")

    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    info = manager.get_info(repo_root=repo_root)
    assert info["session_file"] == str(session_file)
    assert info["repo_root"] == str(repo_root)
