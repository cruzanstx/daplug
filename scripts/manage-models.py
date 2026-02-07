#!/usr/bin/env python3
"""
Model Management Utility for daplug

Lists, checks, and helps add models across all daplug files.

Usage:
    python3 scripts/manage-models.py list          # List all models
    python3 scripts/manage-models.py check         # Check all files for model references
    python3 scripts/manage-models.py add           # Interactive add
    python3 scripts/manage-models.py add <name>    # Add with prompts for details
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Files that contain model references
MODEL_FILES = [
    {
        "path": "skills/prompt-executor/scripts/executor.py",
        "type": "python_dict",
        "description": "Model definitions dict",
        "pattern": r'"(\w+(?:-\w+)*)"\s*:\s*\{[^}]+\}',
    },
    {
        "path": "skills/prompt-executor/scripts/executor.py",
        "type": "argparse_choices",
        "description": "argparse --model choices",
        "pattern": r'choices=\[([^\]]+)\]',
    },
    {
        "path": "skills/prompt-executor/SKILL.md",
        "type": "markdown_list",
        "description": "--model options list",
    },
    {
        "path": "skills/prompt-executor/SKILL.md",
        "type": "markdown_table",
        "description": "Model Reference table",
    },
    {
        "path": "commands/run-prompt.md",
        "type": "markdown_inline",
        "description": "--model argument list",
    },
    {
        "path": "commands/prompts.md",
        "type": "markdown_list",
        "description": "preferred_agent options",
    },
    {
        "path": "commands/create-prompt.md",
        "type": "markdown_section",
        "description": "<available_models> section",
    },
    {
        "path": "commands/create-prompt.md",
        "type": "markdown_table",
        "description": "Recommendation logic table",
    },
    {
        "path": "commands/create-llms-txt.md",
        "type": "markdown_section",
        "description": "<available_models> section",
    },
    {
        "path": "README.md",
        "type": "markdown_table",
        "description": "Model Tiers section",
    },
    {
        "path": "CLAUDE.md",
        "type": "markdown_table",
        "description": "Model Shorthand Reference table",
    },
]


def get_repo_root() -> Path:
    """Get the repository root directory."""
    current = Path(__file__).resolve().parent
    while current != current.parent:
        if (current / ".git").exists():
            return current
        current = current.parent
    return Path(__file__).resolve().parent.parent


def extract_models_from_executor(repo_root: Path) -> Dict[str, dict]:
    """Extract model definitions from executor.py."""
    executor_path = repo_root / "skills/prompt-executor/scripts/executor.py"
    if not executor_path.exists():
        return {}

    content = executor_path.read_text()

    # Find the models dict
    models = {}

    # Match model entries like: "codex": { ... }
    pattern = r'"(\w+(?:-\w+)*)"\s*:\s*\{\s*"command":\s*\[([^\]]+)\][^}]+?"display":\s*"([^"]+)"[^}]+?\}'

    for match in re.finditer(pattern, content, re.DOTALL):
        name = match.group(1)
        command_str = match.group(2)
        display = match.group(3)

        # Parse command list
        commands = re.findall(r'"([^"]+)"', command_str)

        models[name] = {
            "command": commands,
            "display": display,
        }

    return models


def check_model_in_file(repo_root: Path, file_info: dict, model_name: str) -> Tuple[bool, str]:
    """Check if a model is referenced in a file."""
    file_path = repo_root / file_info["path"]
    if not file_path.exists():
        return False, f"File not found: {file_info['path']}"

    content = file_path.read_text()

    # Simple check: is the model name in the file?
    if model_name in content:
        return True, "Found"
    else:
        return False, "Missing"


def list_models(repo_root: Path) -> None:
    """List all models defined in executor.py."""
    models = extract_models_from_executor(repo_root)

    if not models:
        print("No models found in executor.py")
        return

    print(f"Found {len(models)} models:\n")
    print(f"{'Model':<15} {'Display':<50} {'CLI':<10}")
    print("-" * 75)

    for name, info in sorted(models.items()):
        cli = info["command"][0] if info["command"] else "?"
        display = info["display"][:47] + "..." if len(info["display"]) > 50 else info["display"]
        print(f"{name:<15} {display:<50} {cli:<10}")


def check_models(repo_root: Path) -> None:
    """Check all files for model references."""
    models = extract_models_from_executor(repo_root)

    if not models:
        print("No models found in executor.py")
        return

    print("Checking model references across files...\n")

    # Check each model in each file
    all_good = True

    for file_info in MODEL_FILES:
        file_path = repo_root / file_info["path"]
        if not file_path.exists():
            print(f"[SKIP] {file_info['path']} - File not found")
            continue

        content = file_path.read_text()
        missing = []

        for model_name in models.keys():
            # Skip checking for aliases like "local" which maps to "qwen"
            if model_name == "local":
                continue
            if model_name not in content:
                missing.append(model_name)

        if missing:
            all_good = False
            print(f"[WARN] {file_info['path']}")
            print(f"       {file_info['description']}")
            print(f"       Missing: {', '.join(missing)}")
            print()
        else:
            print(f"[OK]   {file_info['path']}")

    print()
    if all_good:
        print("All models are referenced in all files!")
    else:
        print("Some models are missing from files. Run with --verbose for details.")


def add_model_interactive(repo_root: Path) -> None:
    """Interactively add a new model."""
    print("Add New Model\n")
    print("This will guide you through adding a new model to daplug.\n")

    # Get model details
    name = input("Model shorthand name (e.g., 'gpt52', 'gemini-fast'): ").strip()
    if not name:
        print("Error: Model name is required")
        return

    if not re.match(r'^[a-z0-9]+(-[a-z0-9]+)*$', name):
        print("Error: Model name should be lowercase with hyphens (e.g., 'model-name')")
        return

    # Check if model already exists
    models = extract_models_from_executor(repo_root)
    if name in models:
        print(f"Error: Model '{name}' already exists")
        return

    print("\nCLI options:")
    print("  1. codex (OpenAI Codex CLI)")
    print("  2. gemini (Google Gemini CLI)")
    print("  3. custom")

    cli_choice = input("\nChoose CLI [1]: ").strip() or "1"

    if cli_choice == "1":
        cli = "codex"
        model_id = input("OpenAI model ID (e.g., 'gpt-5.2'): ").strip()
        reasoning = input("Reasoning effort (none/high/xhigh) [none]: ").strip() or "none"

        if reasoning == "none":
            command = ["codex", "exec", "--full-auto", "-m", model_id]
        else:
            command = ["codex", "exec", "--full-auto", "-m", model_id, "-c", f'model_reasoning_effort="{reasoning}"']

        stdin_mode = "dash"

    elif cli_choice == "2":
        cli = "gemini"
        model_id = input("Gemini model ID (e.g., 'gemini-3-flash-preview'): ").strip()
        command = ["gemini", "-y", "-m", model_id, "-p"]
        stdin_mode = "arg"

    else:
        cli = input("CLI command name: ").strip()
        command_str = input("Full command (space-separated): ").strip()
        command = command_str.split()
        stdin_mode = input("stdin_mode (dash/arg): ").strip() or "dash"

    display = input(f"Display name (e.g., '{name} (Description)'): ").strip()
    if not display:
        display = f"{name} ({model_id})"

    description = input("Short description (for docs): ").strip()
    if not description:
        description = display

    # Generate the entries
    print("\n" + "=" * 60)
    print("Generated entries to add:\n")

    # Python dict entry
    print("1. Add to executor.py models dict:\n")
    command_str = json.dumps(command)
    print(f'''        "{name}": {{
            "command": {command_str},
            "display": "{display}",
            "env": {{}},
            "stdin_mode": "{stdin_mode}"
        }},''')

    # Argparse choices
    print("\n2. Add to executor.py argparse choices:")
    print(f'    Add "{name}" to the choices list')

    # Markdown table row
    print("\n3. Add to CLAUDE.md Model Shorthand Reference table:")
    print(f"| `{name}` | {cli} | {model_id} |")

    # SKILL.md reference
    print("\n4. Add to SKILL.md Model Reference table:")
    cmd_display = " ".join(command[:5]) + ("..." if len(command) > 5 else "")
    print(f"| {name} | {cmd_display} | {description} |")

    print("\n" + "=" * 60)
    print("\nFiles to update (see CLAUDE.md 'Managing Models' for full list):")
    for i, file_info in enumerate(MODEL_FILES[:6], 1):
        print(f"  {i}. {file_info['path']}")
    print(f"  ... and {len(MODEL_FILES) - 6} more")

    print("\nLocal-family reminder:")
    print("  - If adding a local model (local/qwen/devstral), update router defaults to prefer OpenCode")
    print("    with Codex fallback, and ensure OpenCode LMStudio model IDs are correct.")

    print("\nRun 'python3 scripts/manage-models.py check' after updating to verify.")


def main():
    parser = argparse.ArgumentParser(
        description="Model Management Utility for daplug",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python3 scripts/manage-models.py list
    python3 scripts/manage-models.py check
    python3 scripts/manage-models.py add
        """
    )

    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # list command
    list_parser = subparsers.add_parser("list", help="List all defined models")

    # check command
    check_parser = subparsers.add_parser("check", help="Check model references in all files")

    # add command
    add_parser = subparsers.add_parser("add", help="Add a new model (interactive)")

    args = parser.parse_args()

    repo_root = get_repo_root()

    if args.command == "list":
        list_models(repo_root)
    elif args.command == "check":
        check_models(repo_root)
    elif args.command == "add":
        add_model_interactive(repo_root)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
