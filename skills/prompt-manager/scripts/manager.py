#!/usr/bin/env python3
"""
Prompt Manager - CRUD operations for prompt files.

Centralizes all prompt management logic to avoid shell parsing issues
and provide consistent behavior across /create-prompt, /run-prompt, etc.

Usage:
    python3 manager.py next-number              # Get next available number
    python3 manager.py list [--json]            # List all prompts
    python3 manager.py list --active            # List active prompts only
    python3 manager.py list --completed         # List completed prompts only
    python3 manager.py find <number>            # Find prompt by number
    python3 manager.py read <number>            # Read prompt content
    python3 manager.py create <name> [--number N] [--content-file FILE]
    python3 manager.py complete <number>        # Move to completed/
    python3 manager.py delete <number>          # Delete prompt
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

    def to_dict(self) -> dict:
        return {
            "number": self.number,
            "name": self.name,
            "filename": self.filename,
            "path": str(self.path),
            "status": self.status,
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

    prompts = []

    # List active prompts
    if not completed_only:
        prompts_dir = get_prompts_dir(repo_root)
        if prompts_dir.exists():
            for file in prompts_dir.iterdir():
                if file.is_file() and file.suffix == ".md":
                    parsed = parse_prompt_filename(file.name)
                    if parsed:
                        number, name = parsed
                        prompts.append(PromptInfo(
                            number=number,
                            name=name,
                            filename=file.name,
                            path=file,
                            status="active",
                        ))

    # List completed prompts
    if not active_only:
        completed_dir = get_completed_dir(repo_root)
        if completed_dir.exists():
            for file in completed_dir.iterdir():
                if file.is_file() and file.suffix == ".md":
                    parsed = parse_prompt_filename(file.name)
                    if parsed:
                        number, name = parsed
                        prompts.append(PromptInfo(
                            number=number,
                            name=name,
                            filename=file.name,
                            path=file,
                            status="completed",
                        ))

    # Sort by number
    prompts.sort(key=lambda p: p.number)
    return prompts


def get_next_number(repo_root: Optional[Path] = None) -> str:
    """
    Get the next available prompt number.
    Checks both active and completed prompts to avoid duplicates.

    Returns:
        Three-digit string (e.g., "006")
    """
    prompts = list_prompts(repo_root)

    if not prompts:
        return "001"

    # Find highest number
    highest = max(int(p.number) for p in prompts)
    next_num = highest + 1

    return f"{next_num:03d}"


def find_prompt(number: str, repo_root: Optional[Path] = None) -> Optional[PromptInfo]:
    """
    Find a prompt by its number.

    Args:
        number: Prompt number (can be "6" or "006")
        repo_root: Repository root path

    Returns:
        PromptInfo if found, None otherwise
    """
    # Normalize number to 3 digits
    try:
        normalized = f"{int(number):03d}"
    except ValueError:
        return None

    prompts = list_prompts(repo_root)

    for prompt in prompts:
        if prompt.number == normalized:
            return prompt

    return None


def read_prompt(number: str, repo_root: Optional[Path] = None) -> Optional[str]:
    """
    Read the content of a prompt by its number.

    Returns:
        Prompt content as string, or None if not found
    """
    prompt = find_prompt(number, repo_root)
    if prompt is None:
        return None

    return prompt.path.read_text()


def create_prompt(
    name: str,
    content: str,
    number: Optional[str] = None,
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

    # Generate number if not provided
    if number is None:
        number = get_next_number(repo_root)
    else:
        # Normalize and check for duplicates
        number = f"{int(number):03d}"
        existing = find_prompt(number, repo_root)
        if existing:
            raise ValueError(f"Prompt {number} already exists: {existing.path}")

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
    path = prompts_dir / filename

    # Write content
    path.write_text(content)

    return PromptInfo(
        number=number,
        name=name,
        filename=filename,
        path=path,
        status="active",
    )


def complete_prompt(number: str, repo_root: Optional[Path] = None) -> PromptInfo:
    """
    Move a prompt to the completed directory.

    Args:
        number: Prompt number to complete
        repo_root: Repository root path

    Returns:
        Updated PromptInfo with new path

    Raises:
        FileNotFoundError: If prompt doesn't exist
        ValueError: If prompt is already completed
    """
    prompt = find_prompt(number, repo_root)

    if prompt is None:
        raise FileNotFoundError(f"Prompt {number} not found")

    if prompt.status == "completed":
        raise ValueError(f"Prompt {number} is already completed")

    # Ensure completed directory exists
    if repo_root is None:
        repo_root = get_repo_root()
    completed_dir = ensure_completed_dir(repo_root)

    # Move file
    new_path = completed_dir / prompt.filename
    shutil.move(str(prompt.path), str(new_path))

    return PromptInfo(
        number=prompt.number,
        name=prompt.name,
        filename=prompt.filename,
        path=new_path,
        status="completed",
    )


def delete_prompt(number: str, repo_root: Optional[Path] = None) -> PromptInfo:
    """
    Delete a prompt file.

    Args:
        number: Prompt number to delete
        repo_root: Repository root path

    Returns:
        PromptInfo of deleted prompt

    Raises:
        FileNotFoundError: If prompt doesn't exist
    """
    prompt = find_prompt(number, repo_root)

    if prompt is None:
        raise FileNotFoundError(f"Prompt {number} not found")

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


def main():
    parser = argparse.ArgumentParser(
        description="Prompt Manager - CRUD operations for prompt files"
    )
    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # next-number command
    subparsers.add_parser("next-number", help="Get next available prompt number")

    # list command
    list_parser = subparsers.add_parser("list", help="List prompts")
    list_parser.add_argument("--json", action="store_true", help="Output as JSON")
    list_parser.add_argument("--active", action="store_true", help="Active only")
    list_parser.add_argument("--completed", action="store_true", help="Completed only")

    # find command
    find_parser = subparsers.add_parser("find", help="Find prompt by number")
    find_parser.add_argument("number", help="Prompt number")
    find_parser.add_argument("--json", action="store_true", help="Output as JSON")

    # read command
    read_parser = subparsers.add_parser("read", help="Read prompt content")
    read_parser.add_argument("number", help="Prompt number")

    # create command
    create_parser = subparsers.add_parser("create", help="Create new prompt")
    create_parser.add_argument("name", help="Prompt name (kebab-case)")
    create_parser.add_argument("--number", "-n", help="Specific number (auto if omitted)")
    create_parser.add_argument("--content-file", "-f", help="Read content from file")
    create_parser.add_argument("--content", "-c", help="Prompt content (or use stdin)")
    create_parser.add_argument("--json", action="store_true", help="Output as JSON")

    # complete command
    complete_parser = subparsers.add_parser("complete", help="Move prompt to completed")
    complete_parser.add_argument("number", help="Prompt number")
    complete_parser.add_argument("--json", action="store_true", help="Output as JSON")

    # delete command
    delete_parser = subparsers.add_parser("delete", help="Delete prompt")
    delete_parser.add_argument("number", help="Prompt number")
    delete_parser.add_argument("--json", action="store_true", help="Output as JSON")

    # info command
    info_parser = subparsers.add_parser("info", help="Show prompts directory info")
    info_parser.add_argument("--json", action="store_true", help="Output as JSON")

    args = parser.parse_args()

    try:
        if args.command == "next-number":
            print(get_next_number())

        elif args.command == "list":
            prompts = list_prompts(
                active_only=args.active,
                completed_only=args.completed,
            )
            if args.json:
                print(json.dumps([p.to_dict() for p in prompts], indent=2))
            else:
                if not prompts:
                    print("No prompts found")
                else:
                    for p in prompts:
                        status_marker = "✓" if p.status == "completed" else " "
                        print(f"[{status_marker}] {p.number} - {p.name}")

        elif args.command == "find":
            prompt = find_prompt(args.number)
            if prompt is None:
                print(f"Prompt {args.number} not found", file=sys.stderr)
                sys.exit(1)
            if args.json:
                print(json.dumps(prompt.to_dict(), indent=2))
            else:
                print(prompt.path)

        elif args.command == "read":
            content = read_prompt(args.number)
            if content is None:
                print(f"Prompt {args.number} not found", file=sys.stderr)
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
            )
            if args.json:
                print(json.dumps(prompt.to_dict(), indent=2))
            else:
                print(f"Created: {prompt.path}")

        elif args.command == "complete":
            prompt = complete_prompt(args.number)
            if args.json:
                print(json.dumps(prompt.to_dict(), indent=2))
            else:
                print(f"Completed: {prompt.path}")

        elif args.command == "delete":
            prompt = delete_prompt(args.number)
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
