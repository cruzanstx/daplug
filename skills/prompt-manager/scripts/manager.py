#!/usr/bin/env python3
"""
Prompt Manager - CRUD operations for prompt files.

Centralizes all prompt management logic to avoid shell parsing issues
and provide consistent behavior across /create-prompt, /run-prompt, etc.

Usage:
    python3 manager.py next-number              # Get next available number
    python3 manager.py next-number --folder providers  # Next number within prompts/providers/
    python3 manager.py list [--json]            # List all prompts
    python3 manager.py list --tree              # Tree view grouped by folder
    python3 manager.py list --folder providers  # List prompts in prompts/providers/
    python3 manager.py list --active            # List active prompts only
    python3 manager.py list --completed         # List completed prompts only
    python3 manager.py find <query>             # Find prompt by number, name, or folder/number
    python3 manager.py read <query>             # Read prompt content
    python3 manager.py create <name> [--folder FOLDER] [--number N] [--content-file FILE]
    python3 manager.py complete <query>         # Move prompt to completed/
    python3 manager.py delete <query>           # Delete prompt
    python3 manager.py info                     # Show prompts directory info
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass
class PromptInfo:
    """Information about a prompt file."""
    number: str
    name: str
    filename: str
    path: Path
    status: str  # 'active' or 'completed'
    folder: str  # '' for prompts/, 'providers' for prompts/providers/, 'completed' for prompts/completed/

    def to_dict(self) -> dict:
        return {
            "number": self.number,
            "name": self.name,
            "filename": self.filename,
            "path": str(self.path),
            "status": self.status,
            "folder": self.folder,
        }


def get_repo_root() -> Path:
    """Get the git repository root directory."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            check=True,
        )
        return Path(result.stdout.strip())
    except subprocess.CalledProcessError:
        # Not in a git repo, use current directory
        return Path.cwd()


def get_prompts_dir(repo_root: Optional[Path] = None) -> Path:
    """Get the prompts directory path."""
    if repo_root is None:
        repo_root = get_repo_root()
    return repo_root / "prompts"


def get_completed_dir(repo_root: Optional[Path] = None) -> Path:
    """Get the completed prompts directory path."""
    return get_prompts_dir(repo_root) / "completed"


def ensure_prompts_dir(repo_root: Optional[Path] = None) -> Path:
    """Ensure prompts directory exists and return its path."""
    prompts_dir = get_prompts_dir(repo_root)
    prompts_dir.mkdir(parents=True, exist_ok=True)
    return prompts_dir


def ensure_completed_dir(repo_root: Optional[Path] = None) -> Path:
    """Ensure completed prompts directory exists and return its path."""
    completed_dir = get_completed_dir(repo_root)
    completed_dir.mkdir(parents=True, exist_ok=True)
    return completed_dir


def normalize_folder(folder: Optional[str]) -> str:
    """Normalize a folder argument to a safe, prompts/-relative path.

    Returns '' for root. Rejects absolute paths and path traversal.
    """
    if folder is None:
        return ""

    cleaned = folder.strip().replace("\\", "/").strip("/")
    if cleaned in ("", ".", "./"):
        return ""

    parts: list[str] = [p for p in cleaned.split("/") if p and p != "."]
    if any(p == ".." for p in parts):
        raise ValueError(f"Invalid folder path (path traversal not allowed): {folder}")
    if cleaned.startswith("~") or cleaned.startswith("/"):
        raise ValueError(f"Invalid folder path (must be relative to prompts/): {folder}")

    return "/".join(parts)


def validate_create_folder(folder: str) -> None:
    """Validate a create destination folder (completed/ is reserved)."""
    if folder == "completed" or folder.startswith("completed/"):
        raise ValueError("Folder 'completed' is reserved (archive destination)")


def parse_prompt_filename(filename: str) -> Optional[tuple[str, str]]:
    """
    Parse a prompt filename to extract number and name.
    Returns (number, name) tuple or None if not a valid prompt file.
    """
    match = re.match(r"^(\d{3})-(.+)\.md$", filename)
    if match:
        return match.group(1), match.group(2)
    return None


def list_prompts(
    repo_root: Optional[Path] = None,
    active_only: bool = False,
    completed_only: bool = False,
    folder: Optional[str] = None,
) -> list[PromptInfo]:
    """
    List all prompts in the repository.

    Args:
        repo_root: Repository root path (auto-detected if None)
        active_only: Only list active (non-completed) prompts
        completed_only: Only list completed prompts

    Returns:
        List of PromptInfo objects sorted by number
    """
    if repo_root is None:
        repo_root = get_repo_root()

    prompts: list[PromptInfo] = []

    prompts_dir = get_prompts_dir(repo_root)
    completed_dir = get_completed_dir(repo_root)

    normalized_folder: Optional[str] = None
    if folder is not None:
        normalized_folder = normalize_folder(folder)

    def _folder_sort_key(value: str) -> tuple[int, str]:
        if value == "":
            return (0, "")
        if value == "completed" or value.startswith("completed/"):
            return (2, value)
        return (1, value)

    def _add_prompt(file: Path, status: str) -> None:
        parsed = parse_prompt_filename(file.name)
        if not parsed:
            return
        number, name = parsed
        rel_parent = file.parent.relative_to(prompts_dir) if prompts_dir in file.parents else file.parent
        folder_value = "" if rel_parent == Path(".") else rel_parent.as_posix()
        prompts.append(PromptInfo(
            number=number,
            name=name,
            filename=file.name,
            path=file,
            status=status,
            folder=folder_value,
        ))

    # Folder-filtered listing
    if normalized_folder is not None:
        # completed is special: allow listing it explicitly
        if normalized_folder == "completed" or normalized_folder.startswith("completed/"):
            if completed_only or not active_only:
                if completed_dir.exists():
                    for file in completed_dir.rglob("*.md"):
                        if file.is_file():
                            _add_prompt(file, "completed")
        else:
            if active_only or not completed_only:
                target_dir = prompts_dir if normalized_folder == "" else prompts_dir / normalized_folder
                if target_dir.exists():
                    for file in target_dir.rglob("*.md"):
                        if not file.is_file():
                            continue
                        if completed_dir in file.parents:
                            continue
                        _add_prompt(file, "active")

        prompts.sort(key=lambda p: (_folder_sort_key(p.folder), p.number, p.name))
        return prompts

    # List active prompts across prompts/ (all subfolders except completed/)
    if not completed_only and prompts_dir.exists():
        for file in prompts_dir.rglob("*.md"):
            if not file.is_file():
                continue
            if completed_dir in file.parents:
                continue
            _add_prompt(file, "active")

    # List completed prompts in prompts/completed/
    if not active_only and completed_dir.exists():
        for file in completed_dir.rglob("*.md"):
            if file.is_file():
                _add_prompt(file, "completed")

    prompts.sort(key=lambda p: (_folder_sort_key(p.folder), p.number, p.name))
    return prompts


def get_next_number(repo_root: Optional[Path] = None, folder: Optional[str] = None) -> str:
    """
    Get the next available prompt number.
    By default, checks all prompts (active + completed) to avoid duplicates.

    If folder is provided, the next number is scoped to that folder only
    (i.e., prompts/{folder}/ or prompts/ for root). This enables folder-scoped numbering.

    Returns:
        Three-digit string (e.g., "006")
    """
    if repo_root is None:
        repo_root = get_repo_root()

    # Global numbering (default): avoid duplicates across all prompts and completed/
    if folder is None:
        prompts = list_prompts(repo_root)
        if not prompts:
            return "001"
        highest = max(int(p.number) for p in prompts)
        return f"{highest + 1:03d}"

    # Folder-scoped numbering: scan only within that folder (does not consider completed/)
    normalized_folder = normalize_folder(folder)
    if normalized_folder == "completed" or normalized_folder.startswith("completed/"):
        raise ValueError("Folder-scoped numbering is not supported for 'completed/'")

    prompts_dir = get_prompts_dir(repo_root)
    target_dir = prompts_dir if normalized_folder == "" else prompts_dir / normalized_folder
    if not target_dir.exists():
        return "001"

    candidates: list[PromptInfo] = []
    if normalized_folder == "":
        for file in target_dir.glob("*.md"):
            if file.is_file():
                parsed = parse_prompt_filename(file.name)
                if parsed:
                    number, name = parsed
                    candidates.append(PromptInfo(
                        number=number,
                        name=name,
                        filename=file.name,
                        path=file,
                        status="active",
                        folder="",
                    ))
    else:
        completed_dir = get_completed_dir(repo_root)
        for file in target_dir.rglob("*.md"):
            if not file.is_file():
                continue
            if completed_dir in file.parents:
                continue
            parsed = parse_prompt_filename(file.name)
            if not parsed:
                continue
            number, name = parsed
            rel_parent = file.parent.relative_to(prompts_dir)
            folder_value = "" if rel_parent == Path(".") else rel_parent.as_posix()
            candidates.append(PromptInfo(
                number=number,
                name=name,
                filename=file.name,
                path=file,
                status="active",
                folder=folder_value,
            ))

    if not candidates:
        return "001"

    highest = max(int(p.number) for p in candidates)
    return f"{highest + 1:03d}"


def _format_prompt_ref(prompt: PromptInfo) -> str:
    prefix = f"{prompt.folder}/" if prompt.folder else ""
    return f"{prefix}{prompt.number}-{prompt.name}"


def find_prompt(query: str, repo_root: Optional[Path] = None) -> Optional[PromptInfo]:
    """
    Find a prompt by number or name.

    Supports:
      - "011" (searches all folders; prefers active over completed)
      - "providers/011" (explicit folder)
      - "github-copilot" (name search across folders)

    Args:
        query: Prompt query (number, name, or folder/query)
        repo_root: Repository root path

    Returns:
        PromptInfo if found, None otherwise
    """
    if repo_root is None:
        repo_root = get_repo_root()

    raw = query.strip()
    if not raw:
        raise ValueError("Empty prompt query")

    folder_filter: Optional[str] = None
    token = raw
    if "/" in raw:
        folder_part, token = raw.rsplit("/", 1)
        folder_filter = normalize_folder(folder_part)

    token = token.strip()
    candidates = list_prompts(repo_root, folder=folder_filter) if folder_filter is not None else list_prompts(repo_root)

    matches: list[PromptInfo]
    if token.isdigit():
        normalized = f"{int(token):03d}"
        matches = [p for p in candidates if p.number == normalized]
    else:
        q = token.lower()
        matches = [p for p in candidates if q in p.name.lower() or q in p.filename.lower()]

    if not matches:
        return None

    if folder_filter is not None:
        if len(matches) == 1:
            return matches[0]
        raise ValueError(f"Ambiguous prompt '{raw}': {[_format_prompt_ref(p) for p in matches]}")

    active_matches = [p for p in matches if p.status == "active"]
    if len(active_matches) == 1:
        return active_matches[0]
    if len(active_matches) > 1:
        raise ValueError(f"Ambiguous prompt '{raw}': {[_format_prompt_ref(p) for p in active_matches]}")

    completed_matches = [p for p in matches if p.status == "completed"]
    if len(completed_matches) == 1:
        return completed_matches[0]
    if len(completed_matches) > 1:
        raise ValueError(f"Ambiguous prompt '{raw}': {[_format_prompt_ref(p) for p in completed_matches]}")

    return None


def read_prompt(query: str, repo_root: Optional[Path] = None) -> Optional[str]:
    """
    Read the content of a prompt by query.

    Returns:
        Prompt content as string, or None if not found
    """
    prompt = find_prompt(query, repo_root)
    if prompt is None:
        return None

    return prompt.path.read_text()


def create_prompt(
    name: str,
    content: str,
    number: Optional[str] = None,
    folder: str = "",
    repo_root: Optional[Path] = None,
) -> PromptInfo:
    """
    Create a new prompt file.

    Args:
        name: Descriptive name (will be kebab-cased)
        content: Prompt content
        number: Optional specific number (auto-generated if None)
        repo_root: Repository root path

    Returns:
        PromptInfo for the created prompt

    Raises:
        ValueError: If number already exists
    """
    if repo_root is None:
        repo_root = get_repo_root()

    folder = normalize_folder(folder)
    validate_create_folder(folder)

    # Generate number if not provided
    if number is None:
        number = get_next_number(repo_root)
    else:
        # Normalize (duplicates are checked within target folder)
        number = f"{int(number):03d}"

    # Normalize name to kebab-case
    name = name.lower().strip()
    name = re.sub(r"[^a-z0-9]+", "-", name)
    name = name.strip("-")

    # Limit to 5 words
    words = name.split("-")[:5]
    name = "-".join(words)

    # Create filename and path
    filename = f"{number}-{name}.md"
    prompts_dir = ensure_prompts_dir(repo_root)
    target_dir = prompts_dir if folder == "" else (prompts_dir / folder)
    target_dir.mkdir(parents=True, exist_ok=True)

    # Check for duplicates within target folder
    existing_in_folder = list(target_dir.glob(f"{number}-*.md"))
    if existing_in_folder:
        raise ValueError(f"Prompt {number} already exists in '{folder or 'prompts/'}': {existing_in_folder[0]}")

    # Prevent collisions in completed/ (shutil.move may overwrite)
    completed_path = get_completed_dir(repo_root) / filename
    if completed_path.exists():
        raise ValueError(f"Prompt filename already exists in completed/: {completed_path}")

    path = target_dir / filename

    # Write content
    path.write_text(content)

    return PromptInfo(
        number=number,
        name=name,
        filename=filename,
        path=path,
        status="active",
        folder=folder,
    )


def complete_prompt(query: str, repo_root: Optional[Path] = None) -> PromptInfo:
    """
    Move a prompt to the completed directory.

    Args:
        query: Prompt query (number, name, or folder/number)
        repo_root: Repository root path

    Returns:
        Updated PromptInfo with new path

    Raises:
        FileNotFoundError: If prompt doesn't exist
        ValueError: If prompt is already completed
    """
    prompt = find_prompt(query, repo_root)

    if prompt is None:
        raise FileNotFoundError(f"Prompt {query} not found")

    if prompt.status == "completed":
        raise ValueError(f"Prompt {prompt.number} is already completed")

    # Ensure completed directory exists
    if repo_root is None:
        repo_root = get_repo_root()
    completed_dir = ensure_completed_dir(repo_root)

    # Move file
    new_path = completed_dir / prompt.filename
    if new_path.exists():
        raise ValueError(f"Destination already exists in completed/: {new_path}")
    shutil.move(str(prompt.path), str(new_path))

    return PromptInfo(
        number=prompt.number,
        name=prompt.name,
        filename=prompt.filename,
        path=new_path,
        status="completed",
        folder="completed",
    )


def delete_prompt(query: str, repo_root: Optional[Path] = None) -> PromptInfo:
    """
    Delete a prompt file.

    Args:
        query: Prompt query (number, name, or folder/number)
        repo_root: Repository root path

    Returns:
        PromptInfo of deleted prompt

    Raises:
        FileNotFoundError: If prompt doesn't exist
    """
    prompt = find_prompt(query, repo_root)

    if prompt is None:
        raise FileNotFoundError(f"Prompt {query} not found")

    prompt.path.unlink()
    return prompt


def get_info(repo_root: Optional[Path] = None) -> dict:
    """Get information about the prompts directory."""
    if repo_root is None:
        repo_root = get_repo_root()

    prompts = list_prompts(repo_root)
    active = [p for p in prompts if p.status == "active"]
    completed = [p for p in prompts if p.status == "completed"]

    return {
        "repo_root": str(repo_root),
        "prompts_dir": str(get_prompts_dir(repo_root)),
        "completed_dir": str(get_completed_dir(repo_root)),
        "next_number": get_next_number(repo_root),
        "active_count": len(active),
        "completed_count": len(completed),
        "total_count": len(prompts),
    }


def _print_tree(prompts: list[PromptInfo], repo_root: Path, folder_filter: Optional[str] = None) -> None:
    prompts_dir = get_prompts_dir(repo_root)
    base_dir = prompts_dir
    if folder_filter is not None:
        normalized = normalize_folder(folder_filter)
        base_dir = prompts_dir if normalized == "" else (prompts_dir / normalized)

    def _status_for_file(prompt: PromptInfo) -> str:
        return prompt.status

    # Build tree nodes: {dirs: {name: node}, files: [PromptInfo]}
    def _new_node() -> dict:
        return {"dirs": {}, "files": []}

    root = _new_node()

    for prompt in prompts:
        try:
            rel = prompt.path.relative_to(base_dir)
        except ValueError:
            # Shouldn't happen for normal usage; skip
            continue
        parts = list(rel.parts)
        if not parts:
            continue
        filename = parts.pop()
        node = root
        for part in parts:
            node = node["dirs"].setdefault(part, _new_node())
        node["files"].append(prompt)

    def _sorted_children(node: dict) -> list[tuple[str, str, object]]:
        # Return list of ('file'|'dir', name, obj) with desired ordering:
        # files first, then dirs; completed dir last.
        files = sorted(node["files"], key=lambda p: (p.number, p.name))
        dirs = sorted(node["dirs"].items(), key=lambda item: (item[0] == "completed", item[0]))
        out: list[tuple[str, str, object]] = []
        for p in files:
            out.append(("file", p.filename, p))
        for name, child in dirs:
            out.append(("dir", name, child))
        return out

    def _print_node(node: dict, prefix: str) -> None:
        children = _sorted_children(node)
        for idx, (kind, name, obj) in enumerate(children):
            is_last = idx == len(children) - 1
            connector = "└── " if is_last else "├── "
            next_prefix = prefix + ("    " if is_last else "│   ")
            if kind == "dir":
                print(f"{prefix}{connector}{name}/")
                _print_node(obj, next_prefix)
            else:
                prompt = obj  # type: ignore[assignment]
                print(f"{prefix}{connector}{name} ({_status_for_file(prompt)})")

    root_label = "prompts/"
    if folder_filter is not None:
        normalized = normalize_folder(folder_filter)
        root_label = f"prompts/{normalized}/" if normalized else "prompts/"
    print(root_label)
    _print_node(root, "")


def main():
    parser = argparse.ArgumentParser(
        description="Prompt Manager - CRUD operations for prompt files"
    )
    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # next-number command
    next_parser = subparsers.add_parser("next-number", help="Get next available prompt number")
    next_parser.add_argument("--folder", help="Scope numbering to a folder under prompts/")

    # list command
    list_parser = subparsers.add_parser("list", help="List prompts")
    list_parser.add_argument("--json", action="store_true", help="Output as JSON")
    list_parser.add_argument("--active", action="store_true", help="Active only")
    list_parser.add_argument("--completed", action="store_true", help="Completed only")
    list_parser.add_argument("--folder", help="Filter to a folder under prompts/ (excludes completed/ by default)")
    list_parser.add_argument("--tree", action="store_true", help="Tree view grouped by folder")

    # find command
    find_parser = subparsers.add_parser("find", help="Find prompt by number, name, or folder/number")
    find_parser.add_argument("query", help="Prompt query (e.g. 011, providers/011, github-copilot)")
    find_parser.add_argument("--json", action="store_true", help="Output as JSON")

    # read command
    read_parser = subparsers.add_parser("read", help="Read prompt content")
    read_parser.add_argument("query", help="Prompt query (e.g. 011, providers/011, github-copilot)")

    # create command
    create_parser = subparsers.add_parser("create", help="Create new prompt")
    create_parser.add_argument("name", help="Prompt name (kebab-case)")
    create_parser.add_argument("--number", "-n", help="Specific number (auto if omitted)")
    create_parser.add_argument("--folder", "-f", default="", help="Destination folder under prompts/ (excluding completed/)")
    create_parser.add_argument("--content-file", "-F", help="Read content from file")
    create_parser.add_argument("--content", "-c", help="Prompt content (or use stdin)")
    create_parser.add_argument("--json", action="store_true", help="Output as JSON")

    # complete command
    complete_parser = subparsers.add_parser("complete", help="Move prompt to completed")
    complete_parser.add_argument("query", help="Prompt query (e.g. 011, providers/011, github-copilot)")
    complete_parser.add_argument("--json", action="store_true", help="Output as JSON")

    # delete command
    delete_parser = subparsers.add_parser("delete", help="Delete prompt")
    delete_parser.add_argument("query", help="Prompt query (e.g. 011, providers/011, github-copilot)")
    delete_parser.add_argument("--json", action="store_true", help="Output as JSON")

    # info command
    info_parser = subparsers.add_parser("info", help="Show prompts directory info")
    info_parser.add_argument("--json", action="store_true", help="Output as JSON")

    args = parser.parse_args()

    try:
        if args.command == "next-number":
            print(get_next_number(folder=args.folder))

        elif args.command == "list":
            prompts = list_prompts(
                active_only=args.active,
                completed_only=args.completed,
                folder=args.folder,
            )
            if args.json:
                print(json.dumps([p.to_dict() for p in prompts], indent=2))
            else:
                if args.tree:
                    _print_tree(prompts, get_repo_root(), folder_filter=args.folder)
                elif not prompts:
                    print("No prompts found")
                else:
                    # Group by folder for display
                    grouped: dict[str, list[PromptInfo]] = {}
                    for p in prompts:
                        grouped.setdefault(p.folder, []).append(p)

                    def _display_folder(folder: str) -> str:
                        if folder == "":
                            return "prompts/"
                        return f"prompts/{folder}/"

                    for folder_name in sorted(grouped.keys(), key=lambda f: (f != "", f == "completed" or f.startswith("completed/"), f)):
                        print(_display_folder(folder_name))
                        for p in sorted(grouped[folder_name], key=lambda p: (p.number, p.name)):
                            status_marker = "✓" if p.status == "completed" else " "
                            print(f"  [{status_marker}] {p.number} - {p.name}")

        elif args.command == "find":
            prompt = find_prompt(args.query)
            if prompt is None:
                print(f"Prompt {args.query} not found", file=sys.stderr)
                sys.exit(1)
            if args.json:
                print(json.dumps(prompt.to_dict(), indent=2))
            else:
                print(prompt.path)

        elif args.command == "read":
            content = read_prompt(args.query)
            if content is None:
                print(f"Prompt {args.query} not found", file=sys.stderr)
                sys.exit(1)
            print(content)

        elif args.command == "create":
            # Get content from file, argument, or stdin
            if args.content_file:
                content = Path(args.content_file).read_text()
            elif args.content:
                content = args.content
            elif not sys.stdin.isatty():
                content = sys.stdin.read()
            else:
                print("Error: No content provided. Use --content, --content-file, or pipe via stdin", file=sys.stderr)
                sys.exit(1)

            prompt = create_prompt(
                name=args.name,
                content=content,
                number=args.number,
                folder=args.folder,
            )
            if args.json:
                print(json.dumps(prompt.to_dict(), indent=2))
            else:
                print(f"Created: {prompt.path}")

        elif args.command == "complete":
            prompt = complete_prompt(args.query)
            if args.json:
                print(json.dumps(prompt.to_dict(), indent=2))
            else:
                print(f"Completed: {prompt.path}")

        elif args.command == "delete":
            prompt = delete_prompt(args.query)
            if args.json:
                print(json.dumps(prompt.to_dict(), indent=2))
            else:
                print(f"Deleted: {prompt.filename}")

        elif args.command == "info":
            info = get_info()
            if args.json:
                print(json.dumps(info, indent=2))
            else:
                print(f"Repository root: {info['repo_root']}")
                print(f"Prompts directory: {info['prompts_dir']}")
                print(f"Completed directory: {info['completed_dir']}")
                print(f"Next number: {info['next_number']}")
                print(f"Active prompts: {info['active_count']}")
                print(f"Completed prompts: {info['completed_count']}")
                print(f"Total prompts: {info['total_count']}")

        else:
            parser.print_help()
            sys.exit(1)

    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
