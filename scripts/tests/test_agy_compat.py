#!/usr/bin/env python3
"""Antigravity (agy) plugin-compatibility guards.

`agy plugin install <repo>` converts this Claude Code plugin: commands become
skills, agents are parsed with a strict YAML loader, and any skill body over
24000 bytes is truncated. These tests catch regressions without needing the
agy binary.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
AGY_BODY_LIMIT = 24000
POINTER_RE = re.compile(r"`(?:\$PLUGIN_ROOT/)?((?:skills/[\w-]+/)?references/[\w.-]+\.md)`")


def split_frontmatter(path: Path) -> tuple[list[str] | None, str]:
    text = path.read_text()
    lines = text.split("\n")
    if not lines or lines[0] != "---":
        return None, text
    end = lines.index("---", 1)
    return lines[1:end], "\n".join(lines[end + 1:])


def command_files() -> list[Path]:
    return sorted((REPO_ROOT / "commands").glob("*.md"))


def skill_files() -> list[Path]:
    return sorted((REPO_ROOT / "skills").glob("*/SKILL.md"))


@pytest.mark.parametrize("path", command_files() + skill_files(), ids=lambda p: str(p.relative_to(REPO_ROOT)))
def test_body_fits_agy_skill_limit(path: Path):
    _frontmatter, body = split_frontmatter(path)
    size = len(body.encode())
    assert size < AGY_BODY_LIMIT, (
        f"{path.relative_to(REPO_ROOT)} body is {size} bytes; agy truncates at {AGY_BODY_LIMIT}. "
        "Move a reference section verbatim into references/ and leave a pointer."
    )


@pytest.mark.parametrize("path", skill_files(), ids=lambda p: p.parent.name)
def test_skill_has_name_and_description_frontmatter(path: Path):
    frontmatter, _body = split_frontmatter(path)
    assert frontmatter is not None, f"{path} has no --- frontmatter"
    keys = {line.split(":", 1)[0] for line in frontmatter if re.match(r"^[\w-]+:", line)}
    assert {"name", "description"} <= keys


@pytest.mark.parametrize("path", sorted((REPO_ROOT / "agents").glob("*.md")), ids=lambda p: p.stem)
def test_agent_tools_frontmatter_is_yaml_list(path: Path):
    frontmatter, _body = split_frontmatter(path)
    assert frontmatter is not None
    for index, line in enumerate(frontmatter):
        if not line.startswith("tools:"):
            continue
        value = line[len("tools:"):].strip()
        if value:
            assert value.startswith("[") and value.endswith("]"), f"{path.name}: tools must be a YAML list, got {value!r}"
        else:
            assert index + 1 < len(frontmatter) and frontmatter[index + 1].lstrip().startswith("- ")


def test_no_markdown_in_command_subdirectories():
    """Claude Code loads commands/**/*.md as commands, so references must live elsewhere."""
    nested = [p for p in (REPO_ROOT / "commands").rglob("*.md") if p.parent != REPO_ROOT / "commands"]
    assert nested == []


def test_reference_pointers_resolve():
    for path in command_files() + skill_files():
        text = path.read_text()
        for match in POINTER_RE.finditer(text):
            relative = match.group(1)
            candidates = [REPO_ROOT / relative, path.parent / relative]
            assert any(c.is_file() for c in candidates), f"{path.relative_to(REPO_ROOT)} points at missing {relative}"


def test_every_reference_file_is_pointed_to():
    pointed: set[Path] = set()
    for path in command_files() + skill_files():
        for match in POINTER_RE.finditer(path.read_text()):
            relative = match.group(1)
            for candidate in (REPO_ROOT / relative, path.parent / relative):
                if candidate.is_file():
                    pointed.add(candidate.resolve())
    references = list((REPO_ROOT / "references").glob("*.md")) + list((REPO_ROOT / "skills").glob("*/references/*.md"))
    orphans = [str(p.relative_to(REPO_ROOT)) for p in references if p.resolve() not in pointed]
    assert orphans == []


def test_logo_asset_present():
    logo = REPO_ROOT / "assets" / "logo.svg"
    assert logo.is_file()
    assert "<svg" in logo.read_text()
