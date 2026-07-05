#!/usr/bin/env python3
"""Git worktree creation, dependency installation, and permission management."""

import json
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

from paths import detect_default_branch, get_worktree_dir

def get_existing_worktree(repo_root: Path, branch_name: str) -> str | None:
    """Check if a worktree already exists for the given branch."""
    result = subprocess.run(
        ["git", "worktree", "list", "--porcelain"],
        capture_output=True, text=True, cwd=repo_root
    )

    current_worktree = None
    for line in result.stdout.split('\n'):
        if line.startswith('worktree '):
            current_worktree = line[9:]  # Remove 'worktree ' prefix
        elif line.startswith('branch ') and current_worktree:
            if line.endswith('/' + branch_name) or line == f'branch refs/heads/{branch_name}':
                return current_worktree
            current_worktree = None
    return None


def create_worktree(repo_root: Path, prompt_file: Path, base_branch: Optional[str] = None,
                    on_conflict: str = "error", name_suffix: Optional[str] = None) -> dict:
    """Create a git worktree for the prompt.

    base_branch:
      If None, auto-detect via detect_default_branch (origin/HEAD -> current branch -> "main").
      Pass an explicit value to override.

    name_suffix:
      Optional suffix appended to the branch name and worktree directory, used to
      create multiple distinct worktrees for the same prompt (e.g. --moa per-model
      runs use "moa-<model>").

    on_conflict options:
      - "error": Return conflict info for user decision (default)
      - "remove": Remove existing worktree/branch and create fresh
      - "reuse": Reuse existing worktree if it exists
      - "increment": Create new worktree with incremented suffix (-1, -2, etc.)
    """
    if base_branch is None:
        base_branch = detect_default_branch(repo_root)
    worktrees_dir = get_worktree_dir(repo_root)
    repo_name = repo_root.name
    prompt_num = prompt_file.stem.split("-")[0]
    prompt_slug = prompt_file.stem
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")

    # Include prompt folder in branch name to avoid collisions when prompts are organized
    # into subfolders (and/or folder-scoped numbering is used).
    prompts_dir = repo_root / "prompts"
    branch_folder = ""
    try:
        rel = prompt_file.relative_to(prompts_dir)
        if rel.parent != Path("."):
            branch_folder = rel.parent.as_posix()
    except ValueError:
        branch_folder = ""

    branch_folder = re.sub(r"[^a-zA-Z0-9._/-]+", "-", branch_folder).strip("/")
    branch_name = f"prompt/{branch_folder}/{prompt_slug}" if branch_folder else f"prompt/{prompt_slug}"
    dir_name = f"{repo_name}-prompt-{prompt_num}"
    if name_suffix:
        clean_suffix = re.sub(r"[^a-zA-Z0-9._-]+", "-", name_suffix).strip("-")
        if clean_suffix:
            branch_name = f"{branch_name}-{clean_suffix}"
            dir_name = f"{dir_name}-{clean_suffix}"
    worktree_path = worktrees_dir / f"{dir_name}-{timestamp}"

    # Create worktrees directory
    worktrees_dir.mkdir(parents=True, exist_ok=True)

    # Check if branch already exists
    result = subprocess.run(
        ["git", "branch", "--list", branch_name],
        capture_output=True, text=True, cwd=repo_root
    )
    branch_exists = bool(result.stdout.strip())

    # Check if there's an existing worktree for this branch
    existing_worktree = get_existing_worktree(repo_root, branch_name) if branch_exists else None

    # Handle conflict
    if existing_worktree:
        if on_conflict == "error":
            return {
                "conflict": True,
                "conflict_type": "worktree_exists",
                "existing_worktree": existing_worktree,
                "branch_name": branch_name,
                "options": ["remove", "reuse", "increment"],
                "message": f"Branch '{branch_name}' already has a worktree at '{existing_worktree}'"
            }
        elif on_conflict == "remove":
            # Remove existing worktree and branch
            subprocess.run(
                ["git", "worktree", "remove", existing_worktree, "--force"],
                cwd=repo_root, capture_output=True
            )
            subprocess.run(
                ["git", "branch", "-D", branch_name],
                cwd=repo_root, capture_output=True
            )
            branch_exists = False
        elif on_conflict == "reuse":
            # Reuse existing worktree
            task_file = Path(existing_worktree) / "TASK.md"
            shutil.copy(prompt_file, task_file)
            return {
                "worktree_path": existing_worktree,
                "branch_name": branch_name,
                "task_file": str(task_file),
                "base_branch": base_branch,
                "reused": True
            }
        elif on_conflict == "increment":
            # Find next available suffix
            suffix = 1
            while True:
                new_branch = f"{branch_name}-{suffix}"
                result = subprocess.run(
                    ["git", "branch", "--list", new_branch],
                    capture_output=True, text=True, cwd=repo_root
                )
                if not result.stdout.strip():
                    branch_name = new_branch
                    branch_exists = False
                    break
                existing = get_existing_worktree(repo_root, new_branch)
                if not existing:
                    branch_name = new_branch
                    branch_exists = True
                    break
                suffix += 1

    # Create worktree
    if branch_exists:
        subprocess.run(
            ["git", "worktree", "add", str(worktree_path), branch_name],
            check=True, cwd=repo_root, capture_output=True
        )
    else:
        subprocess.run(
            ["git", "worktree", "add", "-b", branch_name, str(worktree_path), base_branch],
            check=True, cwd=repo_root, capture_output=True
        )

    # Copy prompt as TASK.md
    task_file = worktree_path / "TASK.md"
    shutil.copy(prompt_file, task_file)

    # Install dependencies in the new worktree
    print("[Worktree] Installing dependencies...", file=sys.stderr)
    dep_results = install_worktree_dependencies(worktree_path)
    if dep_results["installed"]:
        print("[Worktree] Dependencies installed successfully", file=sys.stderr)
    elif not dep_results["errors"]:
        print("[Worktree] No dependencies detected", file=sys.stderr)

    return {
        "worktree_path": str(worktree_path),
        "branch_name": branch_name,
        "task_file": str(task_file),
        "base_branch": base_branch,
        "dependencies_installed": dep_results
    }


def install_worktree_dependencies(worktree_path: Path) -> dict:
    """Install dependencies based on detected project type.

    Scans worktree for package managers and installs dependencies.
    Logs progress to stderr for user visibility.

    Returns:
        dict with keys:
        - installed: list of {type, dir, command, duration, success}
        - errors: list of {type, dir, error}
    """
    results = {"installed": [], "errors": []}

    # Define project types with their detection and install logic
    project_types = [
        {
            "type": "npm",
            "lock_file": "package-lock.json",
            "install_cmd": ["npm", "ci"],
            "search_dirs": [".", "frontend", "web", "client", "app"]
        },
        {
            "type": "pnpm",
            "lock_file": "pnpm-lock.yaml",
            "install_cmd": ["pnpm", "install", "--frozen-lockfile"],
            "search_dirs": [".", "frontend", "web", "client", "app"]
        },
        {
            "type": "yarn",
            "lock_file": "yarn.lock",
            "install_cmd": ["yarn", "install", "--frozen-lockfile"],
            "search_dirs": [".", "frontend", "web", "client", "app"]
        },
        {
            "type": "go",
            "lock_file": "go.mod",
            "install_cmd": ["go", "mod", "download"],
            "search_dirs": ["."]
        },
        {
            "type": "pip",
            "lock_file": "requirements.txt",
            "install_cmd": ["pip", "install", "-r", "requirements.txt"],
            "search_dirs": ["."]
        },
        {
            "type": "poetry",
            "lock_file": "poetry.lock",
            "install_cmd": ["poetry", "install"],
            "search_dirs": ["."]
        },
        {
            "type": "uv",
            "lock_file": "uv.lock",
            "install_cmd": ["uv", "sync"],
            "search_dirs": ["."]
        }
    ]

    installed_dirs = set()  # Track dirs we've already installed to avoid duplicates

    for proj in project_types:
        for search_dir in proj["search_dirs"]:
            target_dir = worktree_path / search_dir if search_dir != "." else worktree_path
            lock_file = target_dir / proj["lock_file"]

            if not lock_file.exists():
                continue

            # Skip if we already installed in this directory
            dir_key = str(target_dir.resolve())
            if dir_key in installed_dirs:
                continue
            installed_dirs.add(dir_key)

            print(f"[Worktree]   Detected: {search_dir}/{proj['lock_file']} ({proj['type']})",
                  file=sys.stderr)
            print(f"[Worktree]   Running: {' '.join(proj['install_cmd'])}", file=sys.stderr)

            start_time = time.time()
            try:
                subprocess.run(
                    proj["install_cmd"],
                    cwd=str(target_dir),
                    check=True,
                    capture_output=True,
                    text=True
                )
                duration = time.time() - start_time
                print(f"[Worktree]   {proj['install_cmd'][0]} completed ({duration:.1f}s)",
                      file=sys.stderr)
                results["installed"].append({
                    "type": proj["type"],
                    "dir": search_dir,
                    "command": proj["install_cmd"],
                    "duration": round(duration, 1),
                    "success": True
                })
            except subprocess.CalledProcessError as e:
                duration = time.time() - start_time
                error_msg = e.stderr[:500] if e.stderr else str(e)
                print(f"[Worktree]   {proj['install_cmd'][0]} failed ({duration:.1f}s): {error_msg[:100]}",
                      file=sys.stderr)
                results["errors"].append({
                    "type": proj["type"],
                    "dir": search_dir,
                    "error": error_msg,
                    "duration": round(duration, 1)
                })
            except FileNotFoundError:
                print(f"[Worktree]   {proj['install_cmd'][0]} not found, skipping",
                      file=sys.stderr)
                results["errors"].append({
                    "type": proj["type"],
                    "dir": search_dir,
                    "error": f"{proj['install_cmd'][0]} command not found"
                })

    return results

def normalize_worktree_path(worktree_dir: str, repo_root: str) -> str:
    """Normalize worktree path to absolute, handling relative paths and ~."""
    path = worktree_dir

    # Expand ~ to home directory
    path = os.path.expanduser(path)

    # Make absolute if relative (resolve against repo_root)
    if not os.path.isabs(path):
        path = os.path.join(str(repo_root), path)

    # Normalize . and .. components
    path = os.path.normpath(path)

    # Strip trailing slashes for consistency, but keep root "/"
    if path != "/":
        path = path.rstrip("/")

    return path


def ensure_worktree_permissions(worktree_dir: str, repo_root: str) -> bool:
    """Ensure worktree directory has permissions in Claude settings.

    Returns True if permissions were added, False if already existed.
    """
    abs_path = normalize_worktree_path(worktree_dir, repo_root)
    settings_path = os.path.expanduser("~/.claude/settings.json")

    # Read existing settings
    try:
        with open(settings_path, "r", encoding="utf-8") as f:
            settings = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        settings = {}

    if not isinstance(settings, dict):
        settings = {}

    # Ensure structure exists
    permissions = settings.get("permissions")
    if not isinstance(permissions, dict):
        permissions = {}
        settings["permissions"] = permissions

    allow = permissions.get("allow")
    if not isinstance(allow, list):
        allow = [] if allow is None else [str(allow)]
        permissions["allow"] = allow

    additional = permissions.get("additionalDirectories")
    if not isinstance(additional, list):
        additional = [] if additional is None else [str(additional)]
        permissions["additionalDirectories"] = additional

    changed = False

    allow_set = {str(item) for item in allow}
    for perm in (f"Read({abs_path}/**)", f"Edit({abs_path}/**)", f"Write({abs_path}/**)"):
        if perm not in allow_set:
            allow.append(perm)
            allow_set.add(perm)
            changed = True

    additional_set = {str(item) for item in additional}
    if abs_path not in additional_set:
        additional.append(abs_path)
        changed = True

    if not changed:
        return False

    # Write back only if changes were made
    os.makedirs(os.path.dirname(settings_path), exist_ok=True)
    with open(settings_path, "w", encoding="utf-8") as f:
        json.dump(settings, f, indent=2)
        f.write("\n")

    return True
