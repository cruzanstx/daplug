#!/usr/bin/env python3
"""
Prompt Executor - Prompt resolution, optional worktree creation, and CLI launching.

Resolves prompts from ./prompts/, optionally creates isolated git worktrees,
and launches AI CLI tools. Supports iterative verification loops.
"""

import argparse
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

# Default completion marker
DEFAULT_COMPLETION_MARKER = "VERIFICATION_COMPLETE"


def extract_prompt_title(content: str) -> str:
    """Extract title from prompt content.

    Looks for:
    1. First markdown header (# Title)
    2. First non-empty line if no header
    """
    lines = content.strip().split('\n')
    for line in lines:
        line = line.strip()
        if not line:
            continue
        # Check for markdown header
        if line.startswith('#'):
            # Remove # prefix and clean up
            return line.lstrip('#').strip()
        # Use first non-empty line as title (truncated)
        return line[:80] + ('...' if len(line) > 80 else '')
    return "Untitled prompt"
# Default max iterations for verification loop
DEFAULT_MAX_ITERATIONS = 3
# How often to check log for completion (seconds)
LOOP_CHECK_INTERVAL = 5
# Patterns for detecting suggested next steps in logs
NEXT_STEPS_HEADERS = [
    r"next\s+steps?:",
    r"suggested\s+(?:next\s+)?steps?:",
    r"todo:",
    r"remaining\s+(?:work|tasks?):",
    r"follow[- ]?up(?:\s+tasks?)?:"
]
NEXT_STEPS_HEADER_RE = re.compile(
    r"^\s*(?:" + "|".join(NEXT_STEPS_HEADERS) + r")\s*(?P<inline>.*)$",
    re.IGNORECASE
)
NEXT_STEPS_ITEM_RE = re.compile("^\\s*(?:\\d+[.)]|[-*]|\u2022)\\s*(.+)$")


def get_repo_root() -> Path:
    """Get git repository root."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, check=True
        )
        return Path(result.stdout.strip())
    except subprocess.CalledProcessError:
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


def create_worktree(repo_root: Path, prompt_file: Path, base_branch: str = "main",
                    on_conflict: str = "error") -> dict:
    """Create a git worktree for the prompt.

    on_conflict options:
      - "error": Return conflict info for user decision (default)
      - "remove": Remove existing worktree/branch and create fresh
      - "reuse": Reuse existing worktree if it exists
      - "increment": Create new worktree with incremented suffix (-1, -2, etc.)
    """
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
    worktree_path = worktrees_dir / f"{repo_name}-prompt-{prompt_num}-{timestamp}"

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


def expand_prompt_input(prompt_input: str) -> list[str]:
    """Expand ranges and comma-separated lists into individual prompt identifiers.

    Examples:
        "002-005" -> ["002", "003", "004", "005"]
        "002,005,007" -> ["002", "005", "007"]
        "002-004,010,015-017" -> ["002", "003", "004", "010", "015", "016", "017"]
        "providers/011-013" -> ["providers/011", "providers/012", "providers/013"]
        "001,providers/011,020" -> ["001", "providers/011", "020"]
        "fix-bug" -> ["fix-bug"]  (no expansion, treated as name)
    """
    results = []

    # Split by comma first
    parts = prompt_input.split(",")

    for part in parts:
        part = part.strip()
        if not part:
            continue

        # Check for range pattern (optionally folder-prefixed): "<folder>/001-010" or "001-010"
        range_match = re.match(r'^(?:(?P<folder>.+)/)?(?P<start>\d+)-(?P<end>\d+)$', part)
        if range_match:
            folder = range_match.group("folder")
            start_raw, end_raw = range_match.group("start"), range_match.group("end")
            start, end = int(start_raw), int(end_raw)
            if start > end:
                start, end = end, start  # Allow reverse ranges
            # Preserve zero-padding from the larger number
            width = max(len(start_raw), len(end_raw), 3)
            for n in range(start, end + 1):
                num = str(n).zfill(width)
                results.append(f"{folder}/{num}" if folder else num)
        else:
            results.append(part)

    return results if results else [prompt_input]


def resolve_prompt(prompts_dir: Path, prompt_input: str) -> Path:
    """Resolve a single prompt input to file path."""
    completed_dir = prompts_dir / "completed"

    def _normalize_folder(value: str) -> str:
        cleaned = value.strip().replace("\\", "/").strip("/")
        parts = [p for p in cleaned.split("/") if p and p != "."]
        if any(p == ".." for p in parts):
            raise ValueError(f"Invalid folder path (path traversal not allowed): {value}")
        return "/".join(parts)

    def _iter_prompt_files(search_root: Path, include_completed: bool) -> list[Path]:
        files: list[Path] = []
        for file in search_root.rglob("*.md"):
            if not file.is_file():
                continue
            if file.name.startswith("_"):
                continue
            if not include_completed and completed_dir in file.parents:
                continue
            files.append(file)
        return files

    folder_filter: str | None = None
    token = prompt_input.strip()
    if "/" in token:
        folder_part, token = token.rsplit("/", 1)
        folder_filter = _normalize_folder(folder_part)
        token = token.strip()

    # Determine search root and whether to include completed/
    if folder_filter is None:
        search_root = prompts_dir
        include_completed = False
    else:
        search_root = prompts_dir / folder_filter if folder_filter else prompts_dir
        if not search_root.exists() or not search_root.is_dir():
            raise FileNotFoundError(f"No prompt folder: {folder_filter}")
        include_completed = folder_filter == "completed" or folder_filter.startswith("completed/")

    files = _iter_prompt_files(search_root, include_completed=include_completed)

    # Try as number (e.g., "123" -> "123-*.md")
    if token.isdigit():
        padded = token.zfill(3)
        matches = [f for f in files if f.name.startswith(f"{padded}-")]
        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            rels = [str(m.relative_to(prompts_dir)) for m in matches]
            raise ValueError(f"Ambiguous prompt '{prompt_input}': {rels}")
        raise FileNotFoundError(f"No prompt found for '{prompt_input}'")

    # Try as partial name match
    matches = [f for f in files if token.lower() in f.name.lower()]

    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        rels = [str(m.relative_to(prompts_dir)) for m in matches]
        raise ValueError(f"Ambiguous prompt '{prompt_input}': {rels}")

    raise FileNotFoundError(f"No prompt found for '{prompt_input}'")


def resolve_prompts(prompts_dir: Path, prompt_inputs: list[str]) -> list[Path]:
    """Resolve prompt inputs to file paths.

    Supports ranges and comma-separated lists:
        "002-005" -> prompts 002, 003, 004, 005
        "002,005,007" -> prompts 002, 005, 007
        "002-004,010" -> prompts 002, 003, 004, 010
    """
    if not prompts_dir.exists():
        raise FileNotFoundError(f"No prompts directory: {prompts_dir}")

    # No input = latest prompt
    if not prompt_inputs:
        completed_dir = prompts_dir / "completed"
        prompt_files = [
            p for p in prompts_dir.rglob("*.md")
            if p.is_file()
            and not p.name.startswith("_")
            and completed_dir not in p.parents
        ]
        prompt_files = sorted(prompt_files, key=lambda p: p.stat().st_mtime)
        if not prompt_files:
            raise FileNotFoundError("No prompt files found")
        return [prompt_files[-1]]

    # Filter out flags, then expand ranges/comma-lists
    inputs = [p for p in prompt_inputs if not p.startswith("-")]
    expanded = []
    for inp in inputs:
        expanded.extend(expand_prompt_input(inp))

    # Deduplicate while preserving order
    seen = set()
    unique = []
    for item in expanded:
        if item not in seen:
            seen.add(item)
            unique.append(item)

    return [resolve_prompt(prompts_dir, inp) for inp in unique]


def get_cli_info(model: str) -> dict:
    """Get CLI command and info for a model.

    stdin_mode: How to pass prompt content
      - "dash": Use '-' as last arg, pipe content to stdin (codex)
      - "arg": Pass content as command line argument (gemini)
      - None: Handled by Task subagent (claude)
    """
    models = {
        "codex": {
            "command": ["codex", "exec", "--full-auto"],
            "display": "codex (gpt-5.2-codex)",
            "env": {},
            "stdin_mode": "dash"
        },
        "codex-high": {
            "command": ["codex", "exec", "--full-auto", "-c", 'model_reasoning_effort="high"'],
            "display": "codex-high (gpt-5.2-codex, high reasoning)",
            "env": {},
            "stdin_mode": "dash"
        },
        "codex-xhigh": {
            "command": ["codex", "exec", "--full-auto", "-c", 'model_reasoning_effort="xhigh"'],
            "display": "codex-xhigh (gpt-5.2-codex, xhigh reasoning)",
            "env": {},
            "stdin_mode": "dash"
        },
        "gpt52": {
            "command": ["codex", "exec", "--full-auto", "-m", "gpt-5.2"],
            "display": "gpt52 (GPT-5.2, planning/research)",
            "env": {},
            "stdin_mode": "dash"
        },
        "gpt52-high": {
            "command": ["codex", "exec", "--full-auto", "-m", "gpt-5.2", "-c", 'model_reasoning_effort="high"'],
            "display": "gpt52-high (GPT-5.2, high reasoning)",
            "env": {},
            "stdin_mode": "dash"
        },
        "gpt52-xhigh": {
            "command": ["codex", "exec", "--full-auto", "-m", "gpt-5.2", "-c", 'model_reasoning_effort="xhigh"'],
            "display": "gpt52-xhigh (GPT-5.2, xhigh reasoning, 30+ min tasks)",
            "env": {},
            "stdin_mode": "dash"
        },
        "gemini": {
            "command": ["gemini", "-y", "-m", "gemini-3-flash-preview", "-p"],
            "display": "gemini (Gemini 3 Flash)",
            "env": {},
            "stdin_mode": "arg"  # Gemini takes prompt as -p argument
        },
        "gemini-high": {
            "command": ["gemini", "-y", "-m", "gemini-2.5-pro", "-p"],
            "display": "gemini-high (Gemini 2.5 Pro)",
            "env": {},
            "stdin_mode": "arg"
        },
        "gemini-xhigh": {
            "command": ["gemini", "-y", "-m", "gemini-3-pro-preview", "-p"],
            "display": "gemini-xhigh (Gemini 3 Pro)",
            "env": {},
            "stdin_mode": "arg"
        },
        "gemini25pro": {
            "command": ["gemini", "-y", "-m", "gemini-2.5-pro", "-p"],
            "display": "gemini25pro (Gemini 2.5 Pro)",
            "env": {},
            "stdin_mode": "arg"
        },
        "gemini25flash": {
            "command": ["gemini", "-y", "-m", "gemini-2.5-flash", "-p"],
            "display": "gemini25flash (Gemini 2.5 Flash)",
            "env": {},
            "stdin_mode": "arg"
        },
        "gemini25lite": {
            "command": ["gemini", "-y", "-m", "gemini-2.5-flash-lite", "-p"],
            "display": "gemini25lite (Gemini 2.5 Flash-Lite)",
            "env": {},
            "stdin_mode": "arg"
        },
        "gemini3flash": {
            "command": ["gemini", "-y", "-m", "gemini-3-flash-preview", "-p"],
            "display": "gemini3flash (Gemini 3 Flash Preview)",
            "env": {},
            "stdin_mode": "arg"
        },
        "gemini3pro": {
            "command": ["gemini", "-y", "-m", "gemini-3-pro-preview", "-p"],
            "display": "gemini3pro (Gemini 3 Pro Preview)",
            "env": {},
            "stdin_mode": "arg"
        },
        "zai": {
            "command": ["codex", "exec", "--full-auto", "--profile", "zai"],
            "display": "zai (GLM-4.7)",
            "env": {},
            "stdin_mode": "dash"
        },
        "local": {
            "command": ["codex", "exec", "--full-auto", "--profile", "local"],
            "display": "qwen (local)",
            "env": {"LMSTUDIO_API_KEY": "lm-studio"},
            "stdin_mode": "dash"
        },
        "qwen": {
            "command": ["codex", "exec", "--full-auto", "--profile", "local"],
            "display": "qwen (local)",
            "env": {"LMSTUDIO_API_KEY": "lm-studio"},
            "stdin_mode": "dash"
        },
        "devstral": {
            "command": ["codex", "exec", "--full-auto", "--profile", "local-devstral"],
            "display": "devstral (local)",
            "env": {"LMSTUDIO_API_KEY": "lm-studio"},
            "stdin_mode": "dash"
        },
        "claude": {
            "command": [],  # Handled by Task subagent
            "display": "claude (Claude Sonnet)",
            "env": {},
            "stdin_mode": None
        }
    }
    return models.get(model, models["claude"])


def get_sandbox_add_dirs(cwd: str = None) -> list[str]:
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


def get_loop_state_dir() -> Path:
    """Get the directory for loop state files."""
    state_dir = Path.home() / ".claude" / "loop-state"
    state_dir.mkdir(parents=True, exist_ok=True)
    return state_dir


def get_loop_state_file(prompt_number: str) -> Path:
    """Get the state file path for a prompt's verification loop."""
    return get_loop_state_dir() / f"{prompt_number}.json"


def load_loop_state(prompt_number: str) -> Optional[dict]:
    """Load existing loop state for a prompt."""
    state_file = get_loop_state_file(prompt_number)
    if state_file.exists():
        try:
            return json.loads(state_file.read_text())
        except (json.JSONDecodeError, IOError):
            return None
    return None


def save_loop_state(state: dict) -> None:
    """Save loop state to file."""
    state["last_updated_at"] = datetime.now().isoformat()
    state_file = get_loop_state_file(state["prompt_number"])
    state_file.write_text(json.dumps(state, indent=2))


def create_loop_state(
    prompt_number: str,
    prompt_file: str,
    model: str,
    max_iterations: int,
    completion_marker: str,
    worktree_path: Optional[str] = None,
    branch_name: Optional[str] = None,
    execution_cwd: Optional[str] = None
) -> dict:
    """Create a new loop state structure."""
    return {
        "prompt_number": prompt_number,
        "prompt_file": prompt_file,
        "model": model,
        "worktree_path": worktree_path,
        "branch_name": branch_name,
        "execution_cwd": execution_cwd,
        "iteration": 0,
        "max_iterations": max_iterations,
        "completion_marker": completion_marker,
        "started_at": datetime.now().isoformat(),
        "last_updated_at": datetime.now().isoformat(),
        "status": "pending",  # pending, running, completed, failed, max_iterations_reached
        "history": [],
        "suggested_next_steps": []
    }


def update_loop_iteration(
    state: dict,
    exit_code: int,
    marker_found: bool,
    log_file: str,
    retry_reason: Optional[str] = None
) -> dict:
    """Update loop state after an iteration completes."""
    state["history"].append({
        "iteration": state["iteration"],
        "ended_at": datetime.now().isoformat(),
        "exit_code": exit_code,
        "marker_found": marker_found,
        "retry_reason": retry_reason,
        "log_file": log_file
    })

    if marker_found:
        state["status"] = "completed"
    elif state["iteration"] >= state["max_iterations"]:
        state["status"] = "max_iterations_reached"
    else:
        state["status"] = "running"

    return state


def check_completion_marker(log_file: Path, marker: str) -> tuple[bool, Optional[str]]:
    """Check if the completion marker exists in the log file.

    Returns:
        tuple: (marker_found, retry_reason if NEEDS_RETRY found)

    Note: Only checks for markers AFTER </verification_protocol> to avoid false positives
    from the marker appearing in prompt instructions (which include an example of the tag).
    """
    if not log_file.exists():
        return False, None

    try:
        content = log_file.read_text()

        # Find where the instructions end - only look for markers after that point
        # The verification_protocol section contains example markers that would false-match
        protocol_end = content.rfind("</verification_protocol>")
        if protocol_end != -1:
            # Only search in content after the instructions
            search_content = content[protocol_end:]
        else:
            # No protocol section found (shouldn't happen, but handle gracefully)
            search_content = content

        # Check for NEEDS_RETRY marker first (takes precedence)
        # This ensures explicit retry requests are honored even if completion marker exists
        retry_pattern = r"<verification>\s*NEEDS_RETRY:\s*(.+?)\s*</verification>"
        retry_match = re.search(retry_pattern, search_content, re.IGNORECASE | re.DOTALL)
        if retry_match:
            return False, retry_match.group(1).strip()

        # Check for completion marker in verification tags only
        completion_pattern = rf"<verification>\s*{re.escape(marker)}\s*</verification>"
        if re.search(completion_pattern, search_content, re.IGNORECASE):
            return True, None

        return False, None
    except IOError:
        return False, None


def normalize_next_step_text(text: str) -> str:
    """Normalize next step text for storage and comparison."""
    cleaned = re.sub(r"\s+", " ", text.strip())
    return cleaned.strip(" .;:-")


def normalize_next_step_key(text: str) -> str:
    """Normalize next step text for deduping across iterations."""
    cleaned = re.sub(r"[^\w\s-]", "", text.lower())
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def extract_next_steps(log_file: Path) -> list[dict]:
    """Extract suggested next steps from a log file."""
    if not log_file.exists():
        return []

    try:
        content = log_file.read_text()
    except IOError:
        return []

    lines = content.splitlines()
    steps: list[dict] = []
    index = 0

    def parse_step_lines(step_lines: list[str]) -> list[dict]:
        items: list[dict] = []
        current_text_lines: list[str] = []
        current_original = ""

        def flush_current() -> None:
            nonlocal current_text_lines, current_original
            if not current_text_lines:
                current_original = ""
                return
            text = normalize_next_step_text(" ".join(current_text_lines))
            if text:
                original = current_original or text
                items.append({"text": text, "original": original})
            current_text_lines = []
            current_original = ""

        for raw in step_lines:
            if not raw.strip():
                if current_text_lines:
                    break
                continue

            item_match = NEXT_STEPS_ITEM_RE.match(raw)
            if item_match:
                flush_current()
                current_original = raw.strip()
                current_text_lines = [item_match.group(1).strip()]
                continue

            if current_text_lines:
                continuation = raw.strip()
                if continuation:
                    current_original = f"{current_original} {continuation}" if current_original else continuation
                    current_text_lines.append(continuation)
            else:
                single = raw.strip()
                if single:
                    items.append({
                        "text": normalize_next_step_text(single),
                        "original": single
                    })

        flush_current()

        deduped: list[dict] = []
        seen: set[str] = set()
        for item in items:
            text = item.get("text", "")
            if not text:
                continue
            key = normalize_next_step_key(text)
            if not key or key in seen:
                continue
            seen.add(key)
            deduped.append({"text": text, "original": item.get("original", text)})
        return deduped

    while index < len(lines):
        line = lines[index]
        header_match = NEXT_STEPS_HEADER_RE.match(line)
        if not header_match:
            index += 1
            continue

        inline = header_match.group("inline").strip()
        captured_lines: list[str] = []
        if inline:
            captured_lines.append(inline)

        index += 1
        while index < len(lines):
            current = lines[index]
            if NEXT_STEPS_HEADER_RE.match(current):
                break
            if not current.strip():
                if captured_lines:
                    break
                index += 1
                continue
            captured_lines.append(current)
            index += 1

        steps.extend(parse_step_lines(captured_lines))

    return steps


def merge_suggested_next_steps(state: dict, new_steps: list[dict], iteration: int) -> None:
    """Merge suggested next steps into loop state with dedupe."""
    existing = state.get("suggested_next_steps", [])
    seen = {normalize_next_step_key(step.get("text", "")) for step in existing}

    for step in new_steps:
        text = step.get("text", "")
        if not text:
            continue
        key = normalize_next_step_key(text)
        if not key or key in seen:
            continue
        existing.append({
            "text": text,
            "original": step.get("original", text),
            "source_iteration": iteration
        })
        seen.add(key)

    state["suggested_next_steps"] = existing


def build_previous_iteration_feedback(history: list) -> str:
    """Build a feedback block from prior retry reasons."""
    if not history:
        return ""

    feedback_lines = []
    for entry in history:
        retry_reason = entry.get("retry_reason")
        if retry_reason:
            feedback_lines.append(
                f"Iteration {entry.get('iteration')} ended with: NEEDS_RETRY: {retry_reason}"
            )

    if not feedback_lines:
        return ""

    if len(feedback_lines) > 3:
        feedback_lines = feedback_lines[-3:]

    return "<previous_iteration_feedback>\n" + "\n".join(feedback_lines) + "\n</previous_iteration_feedback>\n\n"


def wrap_prompt_with_verification_protocol(
    content: str,
    iteration: int,
    max_iterations: int,
    completion_marker: str,
    worktree_path: Optional[str] = None,
    branch_name: Optional[str] = None,
    history: list = None
) -> str:
    """Wrap prompt content with verification protocol instructions."""
    history = history or []

    # Build iteration history summary
    history_summary = "None (first iteration)" if not history else "\n".join([
        f"  - Iteration {h['iteration']}: exit_code={h['exit_code']}, marker_found={h['marker_found']}"
        for h in history[-5:]  # Last 5 iterations
    ])

    previous_feedback = build_previous_iteration_feedback(history)

    # Build worktree context
    worktree_context = ""
    if worktree_path:
        worktree_context = f"""Working in isolated worktree: {worktree_path}
Branch: {branch_name or 'unknown'}
"""

    verification_wrapper = f"""<task>
{content}
</task>

<verification_protocol>
## Completion Markers

This task uses iterative verification. You may be re-run multiple times until complete.

**To signal completion:** Output `<verification>{completion_marker}</verification>` ONLY when:
- All implementation is done
- Tests pass (if applicable)
- Build succeeds (if applicable)
- Manual verification steps completed

**To signal retry needed:** Output `<verification>NEEDS_RETRY: [reason]</verification>` if:
- Tests are failing
- Build errors exist
- Implementation incomplete
- Verification steps failed

**Important:**
- Each iteration sees your previous work (files, git history)
- DO NOT output {completion_marker} falsely to exit
- The loop continues until genuine completion or max iterations
- Current iteration: {iteration} of {max_iterations}
</verification_protocol>

{previous_feedback}<environment>
{worktree_context}Previous iterations in this loop:
{history_summary}
</environment>
"""
    return verification_wrapper


def run_cli(cli_info: dict, content: str, cwd: str, log_file: Path) -> dict:
    """Run CLI command in background. Returns execution info.

    Uses stdin_mode to determine how to pass prompts:
    - "dash": Use '-' as last arg, pipe content to stdin (codex)
    - "arg": Pass content as command line argument (gemini)
    """
    if not cli_info["command"]:
        return {"status": "subagent_required"}

    stdin_mode = cli_info.get("stdin_mode", "arg")
    env = os.environ.copy()
    env.update(cli_info["env"])

    log_handle = open(log_file, "w")

    # For codex-based CLIs, add sandbox permissions for common directories
    extra_args = []
    if stdin_mode == "dash" and cli_info["command"] and cli_info["command"][0] == "codex":
        extra_args = get_sandbox_add_dirs(cwd)

    if stdin_mode == "dash":
        # Codex-style: use '-' to read from stdin
        full_cmd = cli_info["command"] + extra_args + ["-"]
        process = subprocess.Popen(
            full_cmd,
            cwd=cwd,
            stdin=subprocess.PIPE,
            stdout=log_handle,
            stderr=subprocess.STDOUT,
            env=env,
            text=True,
            start_new_session=True
        )
        # Write prompt content to stdin and close
        process.stdin.write(content)
        process.stdin.close()
    else:
        # Gemini-style: pass content as argument
        full_cmd = cli_info["command"] + [content]
        process = subprocess.Popen(
            full_cmd,
            cwd=cwd,
            stdout=log_handle,
            stderr=subprocess.STDOUT,
            env=env,
            text=True,
            start_new_session=True
        )

    return {
        "status": "running",
        "pid": process.pid,
        "log": str(log_file)
    }


def run_cli_foreground(cli_info: dict, content: str, cwd: str, log_file: Path) -> dict:
    """Run CLI command in foreground, wait for completion. Returns execution info.

    Used for verification loops where we need to wait and check completion.
    """
    if not cli_info["command"]:
        return {"status": "subagent_required"}

    stdin_mode = cli_info.get("stdin_mode", "arg")
    env = os.environ.copy()
    env.update(cli_info["env"])

    log_handle = open(log_file, "w")

    # For codex-based CLIs, add sandbox permissions for common directories
    extra_args = []
    if stdin_mode == "dash" and cli_info["command"] and cli_info["command"][0] == "codex":
        extra_args = get_sandbox_add_dirs(cwd)

    try:
        if stdin_mode == "dash":
            # Codex-style: use '-' to read from stdin
            full_cmd = cli_info["command"] + extra_args + ["-"]
            process = subprocess.Popen(
                full_cmd,
                cwd=cwd,
                stdin=subprocess.PIPE,
                stdout=log_handle,
                stderr=subprocess.STDOUT,
                env=env,
                text=True
            )
            # Write prompt content to stdin and close
            process.stdin.write(content)
            process.stdin.close()
            exit_code = process.wait()
        else:
            # Gemini-style: pass content as argument
            full_cmd = cli_info["command"] + [content]
            process = subprocess.Popen(
                full_cmd,
                cwd=cwd,
                stdout=log_handle,
                stderr=subprocess.STDOUT,
                env=env,
                text=True
            )
            exit_code = process.wait()

        log_handle.close()
        return {
            "status": "completed",
            "exit_code": exit_code,
            "log": str(log_file)
        }
    except Exception as e:
        log_handle.close()
        return {
            "status": "error",
            "error": str(e),
            "log": str(log_file)
        }


def run_verification_loop(
    cli_info: dict,
    original_content: str,
    cwd: str,
    log_dir: Path,
    prompt_number: str,
    model: str,
    max_iterations: int,
    completion_marker: str,
    worktree_path: Optional[str] = None,
    branch_name: Optional[str] = None
) -> dict:
    """Run CLI in a verification loop until completion marker found or max iterations reached.

    This is the core implementation of the iterative verification system.
    """
    # Create or load existing loop state
    existing_state = load_loop_state(prompt_number)
    if existing_state and existing_state["status"] == "running":
        # Resume from existing state
        state = existing_state
        state.setdefault("history", [])
        state.setdefault("suggested_next_steps", [])
        state["iteration"] += 1
    else:
        # Create new state
        state = create_loop_state(
            prompt_number=prompt_number,
            prompt_file="",  # Will be set by caller
            model=model,
            max_iterations=max_iterations,
            completion_marker=completion_marker,
            worktree_path=worktree_path,
            branch_name=branch_name,
            execution_cwd=cwd
        )
        state["iteration"] = 1

    state["status"] = "running"
    save_loop_state(state)

    result = {
        "loop_enabled": True,
        "iterations": [],
        "final_status": None
    }

    while state["iteration"] <= max_iterations:
        iteration = state["iteration"]
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        log_file = log_dir / f"{model}-{prompt_number}-iter{iteration}-{timestamp}.log"

        # Wrap content with verification protocol
        wrapped_content = wrap_prompt_with_verification_protocol(
            content=original_content,
            iteration=iteration,
            max_iterations=max_iterations,
            completion_marker=completion_marker,
            worktree_path=worktree_path,
            branch_name=branch_name,
            history=state["history"]
        )

        print(f"[Loop] Starting iteration {iteration}/{max_iterations}...", file=sys.stderr)

        # Run CLI and wait for completion
        exec_result = run_cli_foreground(cli_info, wrapped_content, cwd, log_file)

        # Check for completion marker
        marker_found, retry_reason = check_completion_marker(log_file, completion_marker)

        # Extract suggested next steps from this iteration's log
        next_steps = extract_next_steps(log_file)
        if next_steps:
            merge_suggested_next_steps(state, next_steps, iteration)

        # Update state
        exit_code = exec_result.get("exit_code", -1)
        state = update_loop_iteration(
            state,
            exit_code,
            marker_found,
            str(log_file),
            retry_reason=retry_reason
        )

        iteration_result = {
            "iteration": iteration,
            "log_file": str(log_file),
            "exit_code": exit_code,
            "marker_found": marker_found,
            "retry_reason": retry_reason
        }
        result["iterations"].append(iteration_result)

        if marker_found:
            print(f"[Loop] Completion marker found at iteration {iteration}!", file=sys.stderr)
            state["status"] = "completed"
            save_loop_state(state)
            result["final_status"] = "completed"
            break
        elif retry_reason:
            print(f"[Loop] Retry requested: {retry_reason}", file=sys.stderr)

        if state["iteration"] >= max_iterations:
            print(f"[Loop] Max iterations ({max_iterations}) reached without completion.", file=sys.stderr)
            state["status"] = "max_iterations_reached"
            save_loop_state(state)
            result["final_status"] = "max_iterations_reached"
            break

        # Prepare for next iteration
        state["iteration"] += 1
        save_loop_state(state)
        print(f"[Loop] Preparing for iteration {state['iteration']}...", file=sys.stderr)

    result["state_file"] = str(get_loop_state_file(prompt_number))
    result["total_iterations"] = len(result["iterations"])
    result["suggested_next_steps"] = state.get("suggested_next_steps", [])
    return result


def run_verification_loop_background(
    cli_info: dict,
    original_content: str,
    cwd: str,
    log_dir: Path,
    prompt_number: str,
    model: str,
    max_iterations: int,
    completion_marker: str,
    worktree_path: Optional[str] = None,
    branch_name: Optional[str] = None
) -> dict:
    """Start a verification loop in background mode.

    Returns immediately with PID. The loop runs as a separate process.
    """
    # Create initial loop state
    state = create_loop_state(
        prompt_number=prompt_number,
        prompt_file="",
        model=model,
        max_iterations=max_iterations,
        completion_marker=completion_marker,
        worktree_path=worktree_path,
        branch_name=branch_name,
        execution_cwd=cwd
    )
    save_loop_state(state)

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    loop_log = log_dir / f"{model}-{prompt_number}-loop-{timestamp}.log"

    # Build command to run this script with --loop-foreground flag
    script_path = Path(__file__).resolve()
    cmd = [
        sys.executable, str(script_path),
        "--model", model,
        "--run",
        "--loop",
        "--max-iterations", str(max_iterations),
        "--completion-marker", completion_marker,
        "--loop-foreground"  # Internal flag to run in foreground mode
    ]

    if worktree_path:
        # When in worktree, use --prompt-file to read TASK.md directly
        # This avoids the issue where prompts/ directory doesn't exist in worktree
        task_file = Path(worktree_path) / "TASK.md"
        cmd.extend([
            "--prompt-file", str(task_file),
            "--prompt-number", prompt_number,
            "--cwd", cwd
        ])
    else:
        # Normal mode: resolve prompt by number
        cmd.append(prompt_number)

    # Start background process
    log_handle = open(loop_log, "w")
    process = subprocess.Popen(
        cmd,
        cwd=cwd,
        stdout=log_handle,
        stderr=subprocess.STDOUT,
        start_new_session=True
    )

    return {
        "status": "loop_running",
        "pid": process.pid,
        "loop_log": str(loop_log),
        "state_file": str(get_loop_state_file(prompt_number)),
        "max_iterations": max_iterations,
        "completion_marker": completion_marker
    }


def main():
    parser = argparse.ArgumentParser(description="Resolve and execute prompts")
    parser.add_argument("prompts", nargs="*", default=[], help="Prompt number(s) or name(s)")
    parser.add_argument("--model", "-m", default="claude",
                       choices=["claude", "codex", "codex-high", "codex-xhigh",
                               "gpt52", "gpt52-high", "gpt52-xhigh",
                               "gemini", "gemini-high", "gemini-xhigh",
                               "gemini25pro", "gemini25flash", "gemini25lite",
                               "gemini3flash", "gemini3pro", "zai", "local", "qwen", "devstral"],
                       help="Model/CLI to use")
    parser.add_argument("--cwd", "-c", default=None,
                       help="Working directory for execution")
    parser.add_argument("--run", "-r", action="store_true",
                       help="Actually run the CLI (default: just return info)")
    parser.add_argument("--info-only", "-i", action="store_true",
                       help="Only return prompt info, no CLI details")
    parser.add_argument("--worktree", "-w", action="store_true",
                       help="Create isolated git worktree for execution")
    parser.add_argument("--base-branch", "-b", default="main",
                       help="Base branch for worktree (default: main)")
    parser.add_argument("--on-conflict", default="error",
                       choices=["error", "remove", "reuse", "increment"],
                       help="How to handle existing worktree: error (return conflict info), "
                            "remove (delete and recreate), reuse (use existing), "
                            "increment (create with -1, -2 suffix)")

    # Verification loop arguments
    parser.add_argument("--loop", "-l", action="store_true",
                       help="Enable iterative verification loop until completion")
    parser.add_argument("--max-iterations", type=int, default=DEFAULT_MAX_ITERATIONS,
                       help=f"Max iterations before giving up (default: {DEFAULT_MAX_ITERATIONS})")
    parser.add_argument("--completion-marker", default=DEFAULT_COMPLETION_MARKER,
                       help=f"Text pattern that signals completion (default: {DEFAULT_COMPLETION_MARKER})")
    parser.add_argument("--loop-foreground", action="store_true",
                       help="Internal flag: run loop in foreground (used by background spawner)")
    parser.add_argument("--loop-status", action="store_true",
                       help="Check status of an existing verification loop")
    parser.add_argument("--prompt-file", type=str, default=None,
                       help="Read prompt content from file instead of resolving by number (used for worktree loops)")
    parser.add_argument("--prompt-number", type=str, default=None,
                       help="Prompt number to use with --prompt-file (for state/log naming)")

    args = parser.parse_args()

    try:
        repo_root = get_repo_root()
        prompts_dir = repo_root / "prompts"

        # Handle --loop-status: check status of existing loop
        if args.loop_status:
            if not args.prompts:
                # List all active loops
                state_dir = get_loop_state_dir()
                states = []
                for state_file in state_dir.glob("*.json"):
                    try:
                        state = json.loads(state_file.read_text())
                        states.append(state)
                    except (json.JSONDecodeError, IOError):
                        pass
                print(json.dumps({"loop_states": states}, indent=2))
            else:
                # Check specific prompt's loop status
                raw = args.prompts[0].strip()
                token = raw.rsplit("/", 1)[-1]
                if not token.isdigit():
                    print(json.dumps({"error": f"Invalid prompt for --loop-status: {raw}"}))
                    return
                prompt_num = token.zfill(3)
                state = load_loop_state(prompt_num)
                if state:
                    print(json.dumps({"loop_state": state}, indent=2))
                else:
                    print(json.dumps({"error": f"No loop state found for prompt {prompt_num}"}))
            return

        # Handle --prompt-file: read from specific file instead of resolving
        if args.prompt_file:
            prompt_file_path = Path(args.prompt_file)
            if not prompt_file_path.exists():
                raise FileNotFoundError(f"Prompt file not found: {args.prompt_file}")
            prompt_files = [prompt_file_path]
        else:
            prompt_files = resolve_prompts(prompts_dir, args.prompts)

        cli_info = get_cli_info(args.model)
        log_dir = get_cli_logs_dir(repo_root)
        log_dir.mkdir(parents=True, exist_ok=True)

        result = {
            "repo": repo_root.name,
            "model": args.model,
            "cli_display": cli_info["display"],
            "prompts": []
        }

        # Add loop info to result if loop mode enabled
        if args.loop:
            result["loop_mode"] = True
            result["max_iterations"] = args.max_iterations
            result["completion_marker"] = args.completion_marker

        for prompt_file in prompt_files:
            # Use --prompt-number if provided (for worktree loops), otherwise extract from filename
            if args.prompt_number:
                prompt_num = args.prompt_number.zfill(3)
            else:
                prompt_num = prompt_file.stem.split("-")[0]
            timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            log_file = log_dir / f"{args.model}-{prompt_num}-{timestamp}.log"

            content = prompt_file.read_text()

            # Folder/path metadata (supports prompts/ subfolders)
            folder = ""
            status = "active"
            try:
                rel_to_prompts = prompt_file.relative_to(prompts_dir)
                folder_path = rel_to_prompts.parent
                folder = "" if folder_path == Path(".") else folder_path.as_posix()
                if folder == "completed" or folder.startswith("completed/"):
                    status = "completed"
            except ValueError:
                folder = ""
                status = "active"

            try:
                rel_to_repo = prompt_file.relative_to(repo_root)
                prompt_repo_path = rel_to_repo.as_posix()
            except ValueError:
                prompt_repo_path = str(prompt_file)

            prompt_info = {
                "file": str(prompt_file),
                "path": prompt_repo_path,
                "name": prompt_file.name,
                "number": prompt_num,
                "folder": folder,
                "status": status,
                "title": extract_prompt_title(content),
                "content": content,
                "log": str(log_file)
            }

            # Create worktree if requested
            worktree_path = None
            branch_name = None
            if args.worktree:
                worktree_info = create_worktree(repo_root, prompt_file, args.base_branch,
                                                args.on_conflict)
                prompt_info["worktree"] = worktree_info

                # Check for conflict - don't proceed with execution
                if worktree_info.get("conflict"):
                    result["prompts"].append(prompt_info)
                    continue

                # Use worktree as cwd for execution
                execution_cwd = worktree_info["worktree_path"]
                worktree_path = worktree_info["worktree_path"]
                branch_name = worktree_info.get("branch_name")
            else:
                execution_cwd = args.cwd or str(repo_root)

            if not args.info_only:
                prompt_info["cli_command"] = cli_info["command"]
                prompt_info["cli_env"] = cli_info["env"]

            if args.run:
                if args.loop:
                    # Verification loop mode
                    if args.loop_foreground:
                        # Run loop in foreground (called by background spawner or directly)
                        loop_result = run_verification_loop(
                            cli_info=cli_info,
                            original_content=prompt_info["content"],
                            cwd=execution_cwd,
                            log_dir=log_dir,
                            prompt_number=prompt_num,
                            model=args.model,
                            max_iterations=args.max_iterations,
                            completion_marker=args.completion_marker,
                            worktree_path=worktree_path,
                            branch_name=branch_name
                        )
                        prompt_info["execution"] = loop_result
                    else:
                        # Start loop in background
                        loop_result = run_verification_loop_background(
                            cli_info=cli_info,
                            original_content=prompt_info["content"],
                            cwd=execution_cwd,
                            log_dir=log_dir,
                            prompt_number=prompt_num,
                            model=args.model,
                            max_iterations=args.max_iterations,
                            completion_marker=args.completion_marker,
                            worktree_path=worktree_path,
                            branch_name=branch_name
                        )
                        prompt_info["execution"] = loop_result
                else:
                    # Standard single-run mode
                    exec_result = run_cli(cli_info, prompt_info["content"], execution_cwd, log_file)
                    prompt_info["execution"] = exec_result

            result["prompts"].append(prompt_info)

        print(json.dumps(result, indent=2))

    except Exception as e:
        print(json.dumps({"error": str(e)}))
        sys.exit(1)


if __name__ == "__main__":
    main()
