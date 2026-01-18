#!/usr/bin/env python3
"""
Sprint Planner + Executor

Turns a technical specification into:
- Prompt files
- Dependency-aware execution plan
- Persistent state for long-running executions
"""

from __future__ import annotations

import argparse
import contextlib
import dataclasses
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

try:
    from tabulate import tabulate  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    tabulate = None

STATE_SCHEMA_VERSION = 1
STATE_DEFAULT_FILE = ".sprint-state.json"
PROMPT_STATUSES = {"pending", "in_progress", "completed", "failed", "skipped"}

SUBCOMMANDS = {"status", "add", "remove", "replan", "pause", "resume", "cancel", "history"}


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _sha256_hex(data: str) -> str:
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def _slugify(text: str) -> str:
    text = text.strip().lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    text = re.sub(r"-{2,}", "-", text).strip("-")
    return text or "sprint"


def get_repo_root() -> Path:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            check=True,
        )
        return Path(result.stdout.strip())
    except Exception:
        return Path.cwd()


def _read_config_value(repo_root: Path, key: str) -> str | None:
    """Read a config value via config-reader if available."""
    config_reader = repo_root / "skills" / "config-reader" / "scripts" / "config.py"
    if not config_reader.exists():
        return None
    try:
        result = subprocess.run(
            [sys.executable, str(config_reader), "get", key, "--repo-root", str(repo_root), "--quiet"],
            capture_output=True,
            text=True,
            check=False,
        )
        val = result.stdout.strip()
        return val or None
    except Exception:
        return None


def _get_worktrees_dir(repo_root: Path) -> Path:
    configured = _read_config_value(repo_root, "worktree_dir")
    if configured:
        expanded = os.path.expandvars(os.path.expanduser(configured))
        p = Path(expanded)
        if not p.is_absolute():
            return (repo_root / p).resolve()
        return p
    return (repo_root / ".worktrees").resolve()


def _read_text_file(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _write_text_file(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _is_path_like_spec(spec_input: str) -> bool:
    # Heuristic: treat as path if it exists or contains path-ish separators with extension.
    p = Path(spec_input)
    if p.exists():
        return True
    if any(sep in spec_input for sep in ("/", os.sep)) and re.search(r"\.[a-zA-Z0-9]{1,5}$", spec_input):
        return True
    return False


def read_spec(spec_input: str) -> tuple[str, str]:
    """Return (spec_content, spec_path). spec_path may be 'inline'."""
    if _is_path_like_spec(spec_input):
        p = Path(spec_input).expanduser()
        if not p.exists():
            raise FileNotFoundError(f"Spec file not found: {spec_input}")
        return _read_text_file(p), str(p)
    return spec_input, "inline"


def _extract_project_hint(spec_content: str, spec_path: str) -> str:
    if spec_path != "inline":
        return Path(spec_path).stem
    for line in spec_content.splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith("#"):
            return line.lstrip("#").strip()[:80]
        return line[:80]
    return "sprint"


def _default_sprint_id(spec_content: str, spec_path: str, created_at_iso: str) -> str:
    project_hint = _slugify(_extract_project_hint(spec_content, spec_path))
    date = created_at_iso.split("T", 1)[0]
    return f"{project_hint}-{date}"


def _load_json(path: Path) -> Any:
    return json.loads(_read_text_file(path))


@contextlib.contextmanager
def _state_lock(state_file: Path):
    """Best-effort inter-process lock via flock on a sibling lock file."""
    lock_path = state_file.with_suffix(state_file.suffix + ".lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with open(lock_path, "a", encoding="utf-8") as f:
        try:
            import fcntl  # Linux/Unix only

            fcntl.flock(f.fileno(), fcntl.LOCK_EX)
        except Exception:
            pass
        try:
            yield
        finally:
            try:
                import fcntl  # type: ignore

                fcntl.flock(f.fileno(), fcntl.LOCK_UN)
            except Exception:
                pass


def _atomic_write_json(path: Path, data: Any) -> None:
    tmp = path.with_name(path.name + f".tmp.{os.getpid()}")
    _write_text_file(tmp, json.dumps(data, indent=2, sort_keys=True))
    os.replace(tmp, path)


@dataclass
class SprintState:
    sprint_id: str
    created_at: str
    spec_hash: str
    spec_path: str
    prompts: list[dict]
    current_phase: int
    total_phases: int
    model_usage: dict
    paused_at: str | None
    schema_version: int = STATE_SCHEMA_VERSION
    # Optional fields used by replanning/execution
    output_dir: str = "./prompts/"
    plan_file: str = "./sprint-plan.md"
    phases: list[list[str]] = dataclasses.field(default_factory=list)
    dependencies: dict[str, list[str]] = dataclasses.field(default_factory=dict)
    options: dict = dataclasses.field(default_factory=dict)

    @staticmethod
    def from_dict(raw: dict) -> "SprintState":
        return SprintState(
            sprint_id=raw["sprint_id"],
            created_at=raw["created_at"],
            spec_hash=raw.get("spec_hash", ""),
            spec_path=raw.get("spec_path", "inline"),
            prompts=list(raw.get("prompts", [])),
            current_phase=int(raw.get("current_phase", 1)),
            total_phases=int(raw.get("total_phases", 0)),
            model_usage=dict(raw.get("model_usage", {})),
            paused_at=raw.get("paused_at"),
            schema_version=int(raw.get("schema_version", STATE_SCHEMA_VERSION)),
            output_dir=raw.get("output_dir", "./prompts/"),
            plan_file=raw.get("plan_file", "./sprint-plan.md"),
            phases=list(raw.get("phases", [])),
            dependencies=dict(raw.get("dependencies", {})),
            options=dict(raw.get("options", {})),
        )

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)


def load_state(state_file: str = STATE_DEFAULT_FILE) -> SprintState | None:
    path = Path(state_file)
    if not path.exists():
        return None
    try:
        raw = _load_json(path)
        return SprintState.from_dict(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"State file is not valid JSON: {state_file} ({exc})") from exc
    except KeyError as exc:
        raise RuntimeError(f"State file missing required key: {exc}") from exc


def save_state(state: SprintState, state_file: str = STATE_DEFAULT_FILE) -> None:
    path = Path(state_file)
    with _state_lock(path):
        _atomic_write_json(path, state.to_dict())


def update_prompt_status(state: SprintState, prompt_id: str, status: str) -> None:
    if status not in PROMPT_STATUSES:
        raise ValueError(f"Invalid status '{status}'. Expected one of: {sorted(PROMPT_STATUSES)}")
    for p in state.prompts:
        if str(p.get("id")) == str(prompt_id):
            p["status"] = status
            if status == "in_progress" and not p.get("started_at"):
                p["started_at"] = _now_iso()
            if status in {"completed", "failed", "skipped"}:
                p["finished_at"] = _now_iso()
            return
    raise KeyError(f"No prompt with id {prompt_id} in state")


def _format_table(rows: list[list[Any]], headers: list[str]) -> str:
    if tabulate:
        return tabulate(rows, headers=headers, tablefmt="github")
    # Minimal fallback formatting
    widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(str(cell)))
    parts = []
    parts.append(" | ".join(h.ljust(widths[i]) for i, h in enumerate(headers)))
    parts.append("-|-".join("-" * w for w in widths))
    for row in rows:
        parts.append(" | ".join(str(c).ljust(widths[i]) for i, c in enumerate(row)))
    return "\n".join(parts)


def analyze_spec(spec_content: str) -> dict:
    """Heuristic spec parser that identifies components and (lightweight) dependencies."""
    components: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None

    header_re = re.compile(r"^(#{2,3})\s+(.+?)\s*$")
    for line in spec_content.splitlines():
        m = header_re.match(line.strip())
        if m:
            if current:
                components.append(current)
            title = m.group(2).strip()
            current = {"title": title, "slug": _slugify(title), "lines": []}
        else:
            if current is None:
                current = {"title": "Overview", "slug": "overview", "lines": []}
            current["lines"].append(line)
    if current:
        components.append(current)

    for c in components:
        c["text"] = "\n".join(c.pop("lines", []))

    title_by_slug = {c["slug"]: c["title"] for c in components}
    slugs = [c["slug"] for c in components]

    deps: dict[str, list[str]] = {slug: [] for slug in slugs}

    def add_dep(src: str, dst: str) -> None:
        if dst == src:
            return
        if dst not in deps[src]:
            deps[src].append(dst)

    # Explicit dependency phrases
    dep_phrase_re = re.compile(r"\b(?:depends on|requires|after|needs)\b\s+([a-z0-9 _/-]+)", re.I)
    for c in components:
        src = c["slug"]
        text = (c.get("text") or "").lower()
        for m in dep_phrase_re.finditer(text):
            target = _slugify(m.group(1))
            for slug in slugs:
                if slug == target or target in slug or slug in target:
                    add_dep(src, slug)

        # Mention-based: if section mentions another section title
        for other_slug, other_title in title_by_slug.items():
            if other_slug == src:
                continue
            if other_title.lower() in text:
                add_dep(src, other_slug)

    # Simple implicit ordering heuristics
    slug_set = set(slugs)
    def has(s: str) -> bool:
        return s in slug_set

    for c in components:
        src = c["slug"]
        if ("auth" in src or "authentication" in src) and has("database"):
            add_dep(src, "database")
        if ("api" in src or "backend" in src) and (has("auth") or has("authentication")):
            add_dep(src, "auth" if has("auth") else "authentication")
        if ("frontend" in src or "ui" in src) and (has("api") or has("backend")):
            add_dep(src, "api" if has("api") else "backend")

    return {"components": components, "dependencies": deps}


def _parse_prompt_dependencies(prompt_text: str) -> list[str]:
    deps: set[str] = set()
    # e.g. "Depends on: 001, 002" or "depends on 001"
    for line in prompt_text.splitlines():
        m = re.match(r"^\s*depends\s+on\s*:\s*(.+?)\s*$", line, re.I)
        if m:
            ids = re.findall(r"\b\d{1,3}\b", m.group(1))
            deps.update(i.zfill(3) for i in ids)
    # fallback: any explicit "depends on 001" mentions
    for m in re.finditer(r"\bdepends\s+on\b[^0-9]*(\d{1,3})\b", prompt_text, re.I):
        deps.add(m.group(1).zfill(3))
    # Additional common phrasings: "requires prompt 002", "after 003 is complete", "once 004 is done"
    for m in re.finditer(
        r"\b(?:requires|needs)\b[^0-9]{0,40}\b(?:prompt|task)?\b[^0-9]{0,40}(\d{1,3})\b",
        prompt_text,
        re.I,
    ):
        deps.add(m.group(1).zfill(3))
    for m in re.finditer(r"\bafter\b[^0-9]{0,40}\b(?:prompt|task)?\b[^0-9]{0,40}(\d{1,3})\b", prompt_text, re.I):
        deps.add(m.group(1).zfill(3))
    for m in re.finditer(r"\bonce\b[^0-9]{0,60}\b(\d{1,3})\b[^\n]{0,80}\b(?:done|complete|completed)\b", prompt_text, re.I):
        deps.add(m.group(1).zfill(3))
    return sorted(deps)


def parse_prompt_range(spec: str | None) -> list[str]:
    """
    Parse comma-separated prompt numbers/ranges (e.g., "001-005,010") into sorted 3-digit IDs.
    """
    if not spec:
        return []
    ids: set[str] = set()
    parts = [p.strip() for p in spec.split(",") if p.strip()]
    for part in parts:
        m = re.fullmatch(r"(\d{1,3})\s*-\s*(\d{1,3})", part)
        if m:
            start = int(m.group(1))
            end = int(m.group(2))
            if start > end:
                start, end = end, start
            for n in range(start, end + 1):
                ids.add(str(n).zfill(3))
            continue
        m = re.fullmatch(r"\d{1,3}", part)
        if m:
            ids.add(part.zfill(3))
            continue
        raise ValueError(f"Invalid prompt range token: '{part}' (expected N or N-M)")
    return sorted(ids)


def discover_existing_prompts(
    prompts_dir: Path,
    include: str | None = None,
    folder: str | None = None,
    exclude: str | None = None,
) -> list[dict]:
    """
    Find existing prompts based on filters.

    Returns list of prompt dicts with:
    - number: prompt number (e.g., "001")
    - name: full filename
    - path: absolute path
    - content: prompt content
    - folder: subfolder (empty string for root)
    """
    base = prompts_dir.expanduser()
    if not base.is_absolute():
        base = (Path.cwd() / base).resolve()
    if not base.exists() or not base.is_dir():
        raise FileNotFoundError(f"Prompts directory not found: {base}")

    include_ids = set(parse_prompt_range(include)) if include else None
    exclude_ids = set(parse_prompt_range(exclude)) if exclude else set()

    completed_dir = (base / "completed").resolve()

    search_root = base
    include_completed = False
    if folder:
        candidate = (base / folder).resolve()
        try:
            candidate.relative_to(base.resolve())
        except ValueError as exc:
            raise ValueError(f"--folder must be a subfolder of {base}: {folder}") from exc
        if not candidate.exists() or not candidate.is_dir():
            raise FileNotFoundError(f"No prompt folder: {folder}")
        search_root = candidate
        cleaned = str(folder).replace("\\", "/").strip("/")
        include_completed = cleaned == "completed" or cleaned.startswith("completed/")

    def collect_files(include_completed_flag: bool) -> list[Path]:
        files: list[Path] = []
        for p in sorted(search_root.rglob("*.md")):
            m = re.match(r"^(\d{1,3})-", p.name)
            if not m:
                continue
            if not include_completed_flag and completed_dir in p.resolve().parents:
                continue
            files.append(p)
        return files

    prompt_files = collect_files(include_completed)
    # Convenience fallback: if user didn't specify a folder and there are no active prompts,
    # include completed/ so `--from-existing` can still operate on repos that only have archived prompts.
    if not folder and not prompt_files:
        prompt_files = collect_files(True)

    prompts: list[dict] = []
    for p in prompt_files:
        m = re.match(r"^(\d{1,3})-", p.name)
        if not m:
            continue
        number = m.group(1).zfill(3)
        if include_ids is not None and number not in include_ids:
            continue
        if number in exclude_ids:
            continue
        rel = ""
        try:
            rel_path = p.resolve().relative_to(base.resolve())
            rel = "" if rel_path.parent == Path(".") else rel_path.parent.as_posix()
        except Exception:
            rel = ""
        prompts.append(
            {
                "number": number,
                "name": p.name,
                "path": str(p.resolve()),
                "content": _read_text_file(p),
                "folder": rel,
            }
        )

    # Compute a stable execution reference for each prompt.
    # Prefer numeric refs (e.g., "011" or "providers/011"), but disambiguate duplicates by falling back to stem.
    by_ref_number: dict[str, list[dict]] = {}
    for pr in prompts:
        folder_part = str(pr.get("folder") or "").strip("/")
        num = str(pr.get("number") or "")
        ref_number = f"{folder_part}/{num}" if folder_part else num
        pr["ref_number"] = ref_number
        by_ref_number.setdefault(ref_number, []).append(pr)

    for ref_number, items in by_ref_number.items():
        if len(items) == 1:
            items[0]["ref"] = ref_number
            continue
        for pr in items:
            folder_part = str(pr.get("folder") or "").strip("/")
            stem = Path(str(pr.get("name") or "")).stem
            pr["ref"] = f"{folder_part}/{stem}" if folder_part else stem

    # Final sanity check: refs must be unique.
    ref_counts: dict[str, int] = {}
    for pr in prompts:
        r = str(pr.get("ref") or "")
        if not r:
            continue
        ref_counts[r] = ref_counts.get(r, 0) + 1
    dup_refs = {r for r, c in ref_counts.items() if c > 1}
    if dup_refs:
        details = []
        for r in sorted(dup_refs):
            matches = [p for p in prompts if str(p.get("ref")) == r]
            paths = ", ".join(sorted(str(m.get("path")) for m in matches))
            details.append(f"{r}: {paths}")
        raise ValueError("Duplicate prompt references detected; cannot disambiguate. " + " | ".join(details))

    prompts.sort(key=lambda d: (int(str(d.get("number", "0"))), str(d.get("ref") or "")))
    return prompts


def _extract_section(content: str, name: str) -> str | None:
    # Tag-based first: <name>...</name>
    m = re.search(rf"<{re.escape(name)}>(.*?)</{re.escape(name)}>", content, re.I | re.S)
    if m:
        return m.group(1).strip()

    # Heading-based fallback: ## Name ... until next heading at same/higher level.
    header_re = re.compile(rf"^(?P<level>#{1,6})\s+{re.escape(name)}\b.*$", re.I | re.M)
    mh = header_re.search(content)
    if not mh:
        return None
    level = len(mh.group("level"))
    start = mh.end()
    tail = content[start:]
    next_header = re.search(rf"^#{{1,{level}}}\s+\S", tail, re.M)
    chunk = tail[: next_header.start()] if next_header else tail
    return chunk.strip()


def _extract_title_from_prompt_content(content: str) -> str | None:
    objective = _extract_section(content, "objective")
    if objective:
        # Use first non-empty line from objective.
        for line in objective.splitlines():
            line = line.strip()
            if line:
                return line[:160]

    for line in content.splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith("#"):
            return line.lstrip("#").strip()[:160]
        break
    return None


def _extract_paths(text: str) -> tuple[list[str], list[str]]:
    """
    Return (at_paths, tick_paths) extracted from @file and `file` references.
    """
    at_paths: set[str] = set()
    tick_paths: set[str] = set()

    for m in re.finditer(r"@([A-Za-z0-9_./-]+)", text):
        p = m.group(1).strip()
        if p.startswith("./"):
            p = p[2:]
        if p:
            at_paths.add(p)

    for m in re.finditer(r"`([^`\n]+)`", text):
        token = m.group(1).strip()
        if "/" not in token and not re.search(r"\.[a-zA-Z0-9]{1,5}$", token):
            continue
        if token.startswith("./"):
            token = token[2:]
        tick_paths.add(token)

    return sorted(at_paths), sorted(tick_paths)


def analyze_prompt_content(prompt: dict) -> dict:
    """
    Analyze a prompt file to extract:
    - title/objective (from <objective> tag or first heading)
    - dependencies (from "depends on", "requires prompt 002", etc.)
    - task_type (for model assignment)
    - verification_commands (from <verification> section or heading)
    """
    content = str(prompt.get("content") or "")
    title = _extract_title_from_prompt_content(content) or str(prompt.get("name") or "Untitled")

    deps = _parse_prompt_dependencies(content)

    # Dependencies/Requires section scanning
    for section_name in ("Dependencies", "Requires"):
        section = _extract_section(content, section_name)
        if section:
            ids = re.findall(r"\b\d{1,3}\b", section)
            deps.extend([i.zfill(3) for i in ids])

    deps = sorted(set(deps))

    verification = _extract_section(content, "verification") or ""
    verification_commands: list[str] = []
    for line in verification.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("```"):
            continue
        # Best-effort: capture obvious commands.
        if re.match(r"^(python3|pytest|npm|pnpm|yarn|go|make|cargo|rg|git)\b", line):
            verification_commands.append(line)

    # References + outputs for file-based dependency inference
    at_paths, tick_paths = _extract_paths(content)
    referenced_files = sorted(set(at_paths + tick_paths))

    output_section = _extract_section(content, "output") or ""
    out_at, out_tick = _extract_paths(output_section)
    output_files = sorted(set(out_at + out_tick))

    # Heuristic task type for model assignment
    lowered = content.lower()
    task_type = "implementation"
    if "test" in lowered or "pytest" in lowered:
        task_type = "tests"
    elif "readme" in lowered or "documentation" in lowered or "/docs" in lowered:
        task_type = "docs"
    elif "refactor" in lowered:
        task_type = "refactor"

    return {
        "title": title,
        "dependencies": deps,
        "task_type": task_type,
        "verification_commands": verification_commands,
        "referenced_files": referenced_files,
        "output_files": output_files,
    }


def _next_numbers_in_dir(output_dir: Path, count: int) -> list[str]:
    existing = []
    for p in output_dir.glob("*.md"):
        m = re.match(r"^(\d{3})-", p.name)
        if m:
            existing.append(int(m.group(1)))
    start = (max(existing) + 1) if existing else 1
    return [str(n).zfill(3) for n in range(start, start + count)]


def _prompt_template(title: str, spec_excerpt: str, depends_on: list[str] | None = None) -> str:
    depends_line = f"Depends on: {', '.join(depends_on)}\n\n" if depends_on else ""
    return (
        f"# {title}\n\n"
        f"{depends_line}"
        "## Context\n"
        f"{spec_excerpt.strip()}\n\n"
        "## Objective\n"
        f"Implement: {title}\n\n"
        "## Requirements\n"
        "- Follow existing project patterns.\n"
        "- Add tests if applicable.\n\n"
        "## Acceptance Criteria\n"
        "- [ ] Feature implemented\n"
        "- [ ] Tests updated/added\n\n"
        "## Verification\n"
        "- Run relevant tests/build commands\n"
    )


def _prompt_manager_path(repo_root: Path) -> Path:
    return repo_root / "skills" / "prompt-manager" / "scripts" / "manager.py"


def _create_prompt_via_prompt_manager(repo_root: Path, name: str, content: str, folder: str | None) -> dict:
    manager = _prompt_manager_path(repo_root)
    if not manager.exists():
        raise RuntimeError("prompt-manager not found in repo; cannot create prompts via manager.py")

    cmd = [sys.executable, str(manager), "create", name, "--json"]
    if folder:
        cmd.extend(["--folder", folder])

    # Use content-file to avoid shell quoting issues
    tmp = Path("/tmp") / f"sprint-prompt-{os.getpid()}-{_slugify(name)}.md"
    _write_text_file(tmp, content)
    cmd.extend(["--content-file", str(tmp)])
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, cwd=repo_root, check=True)
    finally:
        with contextlib.suppress(Exception):
            tmp.unlink()
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"prompt-manager returned non-JSON output: {result.stdout[:200]}") from exc


def generate_prompts(analysis: dict, output_dir: str) -> list[dict]:
    repo_root = get_repo_root()
    out = Path(output_dir).expanduser()
    if not out.is_absolute():
        out = (Path.cwd() / out).resolve()

    prompts: list[dict] = []

    # If output_dir is under repo_root/prompts, prefer prompt-manager for numbering.
    prompts_dir = (repo_root / "prompts").resolve()
    use_prompt_manager = False
    folder: str | None = None
    try:
        rel = out.relative_to(prompts_dir)
        use_prompt_manager = True
        folder = "" if rel == Path(".") else rel.as_posix()
    except ValueError:
        use_prompt_manager = False

    components: list[dict] = analysis.get("components", [])
    deps_by_slug: dict[str, list[str]] = analysis.get("dependencies", {}) or {}

    if use_prompt_manager:
        for c in components:
            title = c["title"]
            slug = c["slug"]
            excerpt = (c.get("text") or "").strip()[:800]
            depends_slugs = deps_by_slug.get(slug, [])
            content = _prompt_template(title=title, spec_excerpt=excerpt, depends_on=None)
            created = _create_prompt_via_prompt_manager(repo_root, slug, content, folder=folder)
            prompts.append(
                {
                    "id": str(created.get("number") or created.get("prompt", {}).get("number") or "").zfill(3),
                    "status": "pending",
                    "worktree": None,
                    "merged": False,
                    "model": None,
                    "path": created.get("path") or created.get("prompt", {}).get("path"),
                    "title": title,
                    "depends_on_slugs": depends_slugs,
                    "slug": slug,
                }
            )
        _patch_prompt_depends_on_lines(prompts, deps_by_slug)
        return prompts

    # Fallback: write prompt files directly (supports output_dir anywhere, e.g. /tmp/)
    out.mkdir(parents=True, exist_ok=True)
    numbers = _next_numbers_in_dir(out, len(components))
    for i, c in enumerate(components):
        title = c["title"]
        slug = c["slug"]
        excerpt = (c.get("text") or "").strip()[:800]
        depends_slugs = deps_by_slug.get(slug, [])
        content = _prompt_template(title=title, spec_excerpt=excerpt, depends_on=None)
        filename = f"{numbers[i]}-{slug}.md"
        path = out / filename
        _write_text_file(path, content)
        prompts.append(
            {
                "id": numbers[i],
                "status": "pending",
                "worktree": None,
                "merged": False,
                "model": None,
                "path": str(path),
                "title": title,
                "depends_on_slugs": depends_slugs,
                "slug": slug,
            }
        )
    _patch_prompt_depends_on_lines(prompts, deps_by_slug)
    return prompts


def _patch_prompt_depends_on_lines(prompts: list[dict], deps_by_slug: dict[str, list[str]]) -> None:
    """After prompt IDs are known, embed stable 'Depends on: 001, ...' lines for replanning."""
    slug_to_id = {p.get("slug"): str(p.get("id")).zfill(3) for p in prompts if p.get("slug")}
    for p in prompts:
        slug = p.get("slug")
        if not slug:
            continue
        dep_ids = [slug_to_id[d] for d in deps_by_slug.get(slug, []) if d in slug_to_id]
        dep_ids = sorted(set(dep_ids))
        if not dep_ids:
            continue
        path = p.get("path")
        if not path:
            continue
        file_path = Path(str(path))
        if not file_path.exists():
            continue
        text = _read_text_file(file_path)
        # If already has a Depends on line, leave it alone.
        if re.search(r"^\s*depends\s+on\s*:", text, re.I | re.M):
            continue
        lines = text.splitlines()
        out_lines: list[str] = []
        inserted = False
        for idx, line in enumerate(lines):
            out_lines.append(line)
            if not inserted and idx == 0 and line.startswith("#"):
                # after title line + blank line (if present)
                if len(lines) > 1 and lines[1].strip() == "":
                    out_lines.append("")
                out_lines.append(f"Depends on: {', '.join(dep_ids)}")
                out_lines.append("")
                inserted = True
        if not inserted:
            out_lines.insert(0, f"Depends on: {', '.join(dep_ids)}")
            out_lines.insert(1, "")
        _write_text_file(file_path, "\n".join(out_lines).rstrip() + "\n")


def build_dependency_graph(prompts: list[dict], analysis: dict) -> dict[str, list[str]]:
    """Return prompt-id keyed dependency graph."""
    # If caller provided explicit prompt-id dependencies, use those directly.
    prompt_deps = analysis.get("prompt_dependencies")
    if isinstance(prompt_deps, dict):
        graph: dict[str, list[str]] = {}
        for p in prompts:
            pid = str(p.get("id")).zfill(3)
            raw = prompt_deps.get(pid) or prompt_deps.get(str(p.get("id"))) or []
            if not isinstance(raw, list):
                raw = []
            deps = [str(d).zfill(3) if str(d).isdigit() else str(d) for d in raw]
            graph[pid] = sorted(set(deps))
        return graph

    # Prefer analysis dependencies (component slug graph), mapping to prompt ids by slug.
    slug_to_id = {p.get("slug"): str(p.get("id")).zfill(3) for p in prompts if p.get("slug")}
    deps_by_slug: dict[str, list[str]] = analysis.get("dependencies", {}) or {}

    graph: dict[str, list[str]] = {}
    for p in prompts:
        pid = str(p.get("id")).zfill(3)
        slug = p.get("slug")
        deps: list[str] = []
        for dep_slug in deps_by_slug.get(slug, []):
            if dep_slug in slug_to_id:
                deps.append(slug_to_id[dep_slug])
        graph[pid] = sorted(set(deps))

    # If analysis didn't yield much, parse from prompt content.
    if all(len(v) == 0 for v in graph.values()):
        for p in prompts:
            pid = str(p.get("id")).zfill(3)
            text = ""
            path = p.get("path")
            if path:
                with contextlib.suppress(Exception):
                    text = _read_text_file(Path(path))
            graph[pid] = _parse_prompt_dependencies(text)

    return graph


def _topo_phases(nodes: list[str], deps: dict[str, list[str]]) -> tuple[list[list[str]], list[str]]:
    """Kahn levelization. Returns (phases, leftover_cycle_nodes)."""
    remaining = set(nodes)
    incoming: dict[str, set[str]] = {n: set(deps.get(n, [])) for n in nodes}
    phases: list[list[str]] = []

    while remaining:
        ready = sorted([n for n in remaining if not (incoming.get(n) or set())])
        if not ready:
            # cycle or missing deps
            break
        phases.append(ready)
        for n in ready:
            remaining.remove(n)
        for n in remaining:
            incoming[n] = set(incoming.get(n, set())) - set(ready)

    leftovers = sorted(remaining)
    return phases, leftovers


def _model_for_text(text: str, available_models: list[str]) -> str:
    t = text.lower()
    if any(k in t for k in ("architecture", "design", "state machine", "auth", "authentication", "oauth", "encryption")):
        preferred = "claude"
    elif any(k in t for k in ("integration", "api", "docs", "documentation", "sdk", "third-party")):
        preferred = "gemini"
    else:
        preferred = "codex"

    if preferred in available_models:
        return preferred
    return available_models[0] if available_models else "codex"


def _cclimits_availability() -> dict[str, bool]:
    """Best-effort availability map using `npx cclimits --json` if present."""
    try:
        result = subprocess.run(
            ["npx", "cclimits", "--json"],
            capture_output=True,
            text=True,
            check=False,
        )
    except Exception:
        return {}

    if result.returncode != 0:
        return {}

    try:
        raw = json.loads(result.stdout)
    except json.JSONDecodeError:
        return {}

    availability: dict[str, bool] = {}

    # cclimits JSON varies by version; handle common shapes.
    if isinstance(raw, dict):
        tools = raw.get("tools") or raw.get("limits") or raw
        if isinstance(tools, dict):
            for k, v in tools.items():
                if not isinstance(v, dict):
                    continue
                err = v.get("error") or v.get("errors")
                availability[k] = not bool(err)
        elif isinstance(tools, list):
            for item in tools:
                if isinstance(item, dict) and item.get("name"):
                    availability[str(item["name"])] = not bool(item.get("error"))
    return availability


def assign_models(prompts: list[dict], available_models: list[str]) -> dict[str, str]:
    availability = _cclimits_availability()
    assignments: dict[str, str] = {}
    for p in prompts:
        pid = str(p.get("id")).zfill(3)
        text_parts = [str(p.get("title") or ""), str(p.get("slug") or "")]
        analysis = p.get("analysis")
        if isinstance(analysis, dict):
            if analysis.get("task_type"):
                text_parts.append(str(analysis["task_type"]))
            # Keep this bounded; it's only a hint for model routing.
            refs = analysis.get("referenced_files")
            if isinstance(refs, list) and refs:
                text_parts.append(" ".join(str(r) for r in refs[:10]))
        text = " ".join(text_parts)
        model = _model_for_text(text, available_models)
        if availability:
            # If preferred appears unavailable, fall back to first available in list.
            if availability.get(model) is False:
                for m in available_models:
                    if availability.get(m) is not False:
                        model = m
                        break
        assignments[pid] = model
    return assignments


def _run_prompt_command(prompt_ids: list[str], model: str, options: dict) -> str:
    args = ["run-prompt", *prompt_ids, "--model", model]
    if options.get("worktree"):
        args.append("--worktree")
    if options.get("loop"):
        args.append("--loop")
    if len(prompt_ids) > 1:
        args.append("--parallel")
    return "/" + " ".join(args)


def generate_execution_plan(
    prompts: list[dict],
    dependencies: dict[str, list[str]],
    model_assignments: dict[str, str],
    options: dict,
    sprint_id: str,
) -> tuple[str, list[list[str]]]:
    ids = sorted([str(p.get("id")).zfill(3) for p in prompts])
    phases, leftovers = _topo_phases(ids, dependencies)
    if leftovers:
        phases.append(leftovers)

    summary = {
        "total_prompts": len(ids),
        "phases": len(phases),
    }

    model_counts: dict[str, int] = {}
    for pid in ids:
        m = model_assignments.get(pid, "codex")
        model_counts[m] = model_counts.get(m, 0) + 1

    lines: list[str] = []
    lines.append(f"# Sprint Plan: {sprint_id}")
    lines.append("")
    lines.append("## Summary")
    lines.append(f"- Total Prompts: {summary['total_prompts']}")
    lines.append(f"- Phases: {summary['phases']}")
    lines.append(f"- Models: {', '.join([f'{k} ({v})' for k, v in sorted(model_counts.items())])}")
    lines.append("")
    lines.append("## Execution Plan")
    lines.append("")

    for i, phase in enumerate(phases, start=1):
        lines.append(f"### Phase {i}")
        # Group by model for runnable /run-prompt commands
        groups: dict[str, list[str]] = {}
        for pid in phase:
            groups.setdefault(model_assignments.get(pid, "codex"), []).append(pid)
        for model, pids in sorted(groups.items()):
            lines.append(_run_prompt_command(pids, model=model, options=options))
        lines.append("")

    lines.append("## Dependencies")
    lines.append("")
    for pid in ids:
        deps = dependencies.get(pid, [])
        if deps:
            lines.append(f"- {pid} depends on: {', '.join(deps)}")
    if all(not dependencies.get(pid) for pid in ids):
        lines.append("- (none detected)")
    lines.append("")

    return "\n".join(lines).rstrip() + "\n", phases


def _write_run_sprint_script(
    phases: list[list[str]],
    model_assignments: dict[str, str],
    options: dict,
    output_path: Path,
) -> None:
    """
    Generate a runnable script that executes prompts via prompt-executor.
    """
    import shlex

    lines: list[str] = []
    lines.append("#!/usr/bin/env bash")
    lines.append("set -euo pipefail")
    lines.append("")
    lines.append("# Generated by skills/sprint/scripts/sprint.py")
    lines.append("")

    base_cmd = ["python3", "skills/prompt-executor/scripts/executor.py", "--run"]
    if options.get("loop"):
        base_cmd.extend(
            [
                "--loop",
                "--max-iterations",
                str(int(options.get("max_iterations", 3))),
                "--completion-marker",
                str(options.get("completion_marker", "VERIFICATION_COMPLETE")),
            ]
        )
    if options.get("worktree"):
        base_cmd.extend(["--worktree", "--base-branch", str(options.get("base_branch", "main"))])

    total_phases = len(phases)
    for i, phase in enumerate(phases, start=1):
        lines.append(f'echo "== Phase {i}/{total_phases} =="')
        groups: dict[str, list[str]] = {}
        for pid in phase:
            groups.setdefault(model_assignments.get(pid, "codex"), []).append(pid)
        for model, pids in sorted(groups.items()):
            cmd = [*base_cmd, "--model", model, *pids]
            lines.append(" ".join(shlex.quote(c) for c in cmd))
        lines.append("")

    output_path = output_path.expanduser()
    if not output_path.is_absolute():
        output_path = (Path.cwd() / output_path).resolve()
    _write_text_file(output_path, "\n".join(lines).rstrip() + "\n")
    try:
        os.chmod(output_path, 0o755)
    except Exception:
        pass


def _resolve_prompt_paths(prompts: list[dict], output_dir: str) -> None:
    """Ensure prompt dicts have absolute-ish paths where possible."""
    out = Path(output_dir).expanduser()
    if not out.is_absolute():
        out = (Path.cwd() / out).resolve()
    for p in prompts:
        path = p.get("path")
        if not path:
            # best-effort guess
            guessed = out / f"{str(p.get('id')).zfill(3)}-{p.get('slug')}.md"
            p["path"] = str(guessed)


def _ensure_active_state(state: SprintState | None, state_file: str) -> SprintState:
    if not state:
        raise RuntimeError(f"No active sprint. Run /sprint <spec> first (missing {state_file}).")
    return state


def cmd_status(state_file: str) -> None:
    state = load_state(state_file)
    state = _ensure_active_state(state, state_file)

    completed = sum(1 for p in state.prompts if p.get("status") == "completed")
    failed = sum(1 for p in state.prompts if p.get("status") == "failed")
    skipped = sum(1 for p in state.prompts if p.get("status") == "skipped")
    total = len(state.prompts)

    print(f"Sprint: {state.sprint_id}")
    print(f"Created: {state.created_at}")
    if state.paused_at:
        print(f"Paused:  {state.paused_at}")
    print(f"Phase:   {state.current_phase}/{state.total_phases} (next)")
    print(f"Prompts: {completed}/{total} completed, {failed} failed, {skipped} skipped")
    print("")

    rows: list[list[Any]] = []
    for p in state.prompts:
        rows.append(
            [
                str(p.get("id")).zfill(3),
                p.get("status", "pending"),
                p.get("model") or "-",
                (p.get("worktree") or {}).get("name") if isinstance(p.get("worktree"), dict) else "-",
                "yes" if p.get("merged") else "no",
            ]
        )
    print(_format_table(rows, headers=["id", "status", "model", "worktree", "merged"]))
    print("")

    if state.model_usage:
        usage_rows = [[k, v] for k, v in sorted(state.model_usage.items())]
        print(_format_table(usage_rows, headers=["model", "minutes_used"]))
        print("")

    if state.paused_at:
        print("Next steps:")
        print(f"- Resume: python3 skills/sprint/scripts/sprint.py resume --state-file {state_file}")
        return

    # Suggest next phase commands if we have a plan
    if state.phases and 1 <= state.current_phase <= len(state.phases):
        next_phase = state.phases[state.current_phase - 1]
        pending = [pid for pid in next_phase if _prompt_in_state(state, pid).get("status") == "pending"]
        if pending:
            print("Next steps:")
            # Group by model
            groups: dict[str, list[str]] = {}
            for pid in pending:
                model = _prompt_in_state(state, pid).get("model") or "codex"
                groups.setdefault(model, []).append(pid)
            for model, pids in sorted(groups.items()):
                print(f"- {_run_prompt_command(pids, model=model, options=state.options)}")


def _prompt_in_state(state: SprintState, prompt_id: str) -> dict:
    pid = str(prompt_id).zfill(3)
    for p in state.prompts:
        if str(p.get("id")).zfill(3) == pid:
            return p
    raise KeyError(f"No prompt with id {pid} in state")


def cmd_add(description: str, state_file: str) -> None:
    state = load_state(state_file)
    state = _ensure_active_state(state, state_file)

    repo_root = get_repo_root()
    out = Path(state.output_dir).expanduser()
    if not out.is_absolute():
        out = (Path.cwd() / out).resolve()

    title = description.strip()
    slug = _slugify(title)[:60]
    content = _prompt_template(title=title, spec_excerpt=f"(Added to sprint)\n\n{title}\n")

    prompts_dir = (repo_root / "prompts").resolve()
    created_prompt: dict[str, Any]

    try:
        rel = out.relative_to(prompts_dir)
        folder = "" if rel == Path(".") else rel.as_posix()
        created = _create_prompt_via_prompt_manager(repo_root, slug, content, folder=folder)
        created_prompt = {
            "id": str(created.get("number") or created.get("prompt", {}).get("number") or "").zfill(3),
            "path": created.get("path") or created.get("prompt", {}).get("path"),
        }
    except ValueError:
        # Fallback: write directly
        out.mkdir(parents=True, exist_ok=True)
        next_id = _next_numbers_in_dir(out, 1)[0]
        path = out / f"{next_id}-{slug}.md"
        _write_text_file(path, content)
        created_prompt = {"id": next_id, "path": str(path)}

    state.prompts.append(
        {
            "id": created_prompt["id"],
            "status": "pending",
            "worktree": None,
            "merged": False,
            "model": None,
            "path": created_prompt["path"],
            "title": title,
            "slug": slug,
        }
    )
    save_state(state, state_file)
    cmd_replan(state_file)
    print(f"Added prompt {created_prompt['id']}: {title}")


def cmd_remove(prompt_id: str, state_file: str) -> None:
    state = load_state(state_file)
    state = _ensure_active_state(state, state_file)
    pid = str(prompt_id).zfill(3)

    # Warn if others depend on it
    dependents = [k for k, deps in (state.dependencies or {}).items() if pid in deps]
    if dependents:
        print(f"Warning: prompts depend on {pid}: {', '.join(sorted(dependents))}", file=sys.stderr)

    update_prompt_status(state, pid, "skipped")
    save_state(state, state_file)
    cmd_replan(state_file)
    print(f"Marked {pid} as skipped (file not deleted).")


def cmd_replan(state_file: str) -> None:
    state = load_state(state_file)
    state = _ensure_active_state(state, state_file)

    _resolve_prompt_paths(state.prompts, state.output_dir)

    # Rebuild dependency graph by reading prompt files
    deps: dict[str, list[str]] = {}
    for p in state.prompts:
        pid = str(p.get("id")).zfill(3)
        path = Path(str(p.get("path")))
        text = ""
        with contextlib.suppress(Exception):
            text = _read_text_file(path)
        deps[pid] = [d for d in _parse_prompt_dependencies(text) if d != pid]
    state.dependencies = deps

    models_list = [m.strip() for m in str(state.options.get("models", "claude,codex,gemini")).split(",") if m.strip()]
    assignments = assign_models(state.prompts, models_list)
    for p in state.prompts:
        pid = str(p.get("id")).zfill(3)
        if p.get("status") in {"skipped"}:
            continue
        p["model"] = assignments.get(pid, p.get("model") or "codex")

    # Generate new phases
    ids = sorted([str(p.get("id")).zfill(3) for p in state.prompts if p.get("status") != "skipped"])
    phases, leftovers = _topo_phases(ids, state.dependencies)
    if leftovers:
        phases.append(leftovers)
    state.phases = phases
    state.total_phases = len(phases)
    if state.current_phase < 1:
        state.current_phase = 1
    if state.current_phase > state.total_phases + 1:
        state.current_phase = state.total_phases + 1

    plan_text, _ = generate_execution_plan(
        prompts=[p for p in state.prompts if p.get("status") != "skipped"],
        dependencies=state.dependencies,
        model_assignments={str(k): v for k, v in assignments.items()},
        options=state.options,
        sprint_id=state.sprint_id,
    )
    _write_text_file(Path(state.plan_file), plan_text)
    save_state(state, state_file)


def cmd_pause(state_file: str) -> None:
    state = load_state(state_file)
    state = _ensure_active_state(state, state_file)
    state.paused_at = _now_iso()
    save_state(state, state_file)

    in_progress = [str(p.get("id")).zfill(3) for p in state.prompts if p.get("status") == "in_progress"]
    print(f"Paused sprint {state.sprint_id} at {state.paused_at}")
    if in_progress:
        print(f"In-progress prompts: {', '.join(sorted(in_progress))} (they may still be running)")
    print("")
    print("Resume:")
    print(f"python3 skills/sprint/scripts/sprint.py resume --state-file {state_file}")


def cmd_resume(state_file: str) -> None:
    state = load_state(state_file)
    state = _ensure_active_state(state, state_file)
    if not state.paused_at:
        raise RuntimeError("Sprint is not paused.")

    state.paused_at = None
    save_state(state, state_file)

    if state.options.get("auto_execute"):
        auto_execute(state, state.options, state_file=state_file)
    else:
        print("Sprint unpaused. Run `python3 skills/sprint/scripts/sprint.py --auto-execute ...` to continue execution.")


def _git_current_branch(repo_root: Path) -> str:
    result = subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"],
        capture_output=True,
        text=True,
        cwd=repo_root,
        check=False,
    )
    return result.stdout.strip() or "HEAD"


def _cleanup_worktree(repo_root: Path, worktree_path: str | None, branch_name: str | None) -> None:
    if worktree_path:
        subprocess.run(["git", "worktree", "remove", "--force", worktree_path], cwd=repo_root, check=False)
    if branch_name and branch_name.startswith("sprint/"):
        current = _git_current_branch(repo_root)
        if current != branch_name:
            subprocess.run(["git", "branch", "-D", branch_name], cwd=repo_root, check=False)


def cmd_cancel(state_file: str, yes: bool = False) -> None:
    state = load_state(state_file)
    state = _ensure_active_state(state, state_file)

    if not yes:
        resp = input(f"Cancel sprint '{state.sprint_id}' and remove sprint worktrees? [y/N] ").strip().lower()
        if resp not in {"y", "yes"}:
            print("Cancel aborted.")
            return

    repo_root = get_repo_root()
    for p in state.prompts:
        wt = p.get("worktree")
        if isinstance(wt, dict):
            _cleanup_worktree(repo_root, wt.get("path"), wt.get("branch"))

    completed = sum(1 for p in state.prompts if p.get("status") == "completed")
    failed = sum(1 for p in state.prompts if p.get("status") == "failed")
    skipped = sum(1 for p in state.prompts if p.get("status") == "skipped")

    src = Path(state_file)
    dst = src.with_name(src.name + ".cancelled")
    with contextlib.suppress(Exception):
        os.replace(src, dst)

    print(f"Cancelled sprint {state.sprint_id}")
    print(f"Summary: {completed} completed, {failed} failed, {skipped} skipped")
    print(f"Archived state: {dst}")


def cmd_history(state_dir: str = ".") -> None:
    d = Path(state_dir)
    files = sorted(d.glob(".sprint-state.json*"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not files:
        print("No sprint state files found.")
        return
    current = d / ".sprint-state.json"
    rows = []
    for f in files:
        try:
            raw = _load_json(f)
            state = SprintState.from_dict(raw)
            total = len(state.prompts)
            completed = sum(1 for p in state.prompts if p.get("status") == "completed")
            marker = "*" if f.resolve() == current.resolve() else ""
            rows.append([f.name + marker, state.sprint_id, state.created_at, f"{completed}/{total}"])
        except Exception:
            rows.append([f.name, "-", "-", "-"])
    print(_format_table(rows, headers=["state_file", "sprint_id", "created_at", "completed"]))


def _sprint_worktree_name(sprint_id: str, prompt_id: str) -> str:
    return f"sprint-{_slugify(sprint_id)}-{str(prompt_id).zfill(3)}"


def _create_sprint_worktree(repo_root: Path, sprint_id: str, prompt_id: str, base_branch: str = "main") -> dict:
    name = _sprint_worktree_name(sprint_id, prompt_id)
    worktrees_dir = _get_worktrees_dir(repo_root)
    worktrees_dir.mkdir(parents=True, exist_ok=True)

    branch = f"sprint/{_slugify(sprint_id)}/{str(prompt_id).zfill(3)}"
    path = worktrees_dir / name

    # Handle collision
    if path.exists():
        suffix = 1
        while (worktrees_dir / f"{name}-{suffix}").exists():
            suffix += 1
        name = f"{name}-{suffix}"
        path = worktrees_dir / name
        branch = f"{branch}-{suffix}"

    subprocess.run(
        ["git", "worktree", "add", "-b", branch, str(path), base_branch],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    )
    return {"name": name, "path": str(path), "branch": branch, "base_branch": base_branch}


def _executor_path(repo_root: Path) -> Path:
    return repo_root / "skills" / "prompt-executor" / "scripts" / "executor.py"


def _prompt_ref_from_state_prompt(p: dict) -> str:
    return str(p.get("id")).zfill(3)


def _build_executor_command(repo_root: Path, prompt: dict, model: str, options: dict, state: SprintState) -> list[str]:
    executor = _executor_path(repo_root)
    if not executor.exists():
        raise RuntimeError("prompt-executor not found in repo; cannot auto-execute")

    prompt_id = str(prompt.get("id")).zfill(3)
    prompt_path = Path(str(prompt.get("path")))
    if not prompt_path.exists():
        raise RuntimeError(f"Prompt file missing for {prompt_id}: {prompt_path}")

    cmd: list[str] = [sys.executable, str(executor), "--model", model, "--run"]

    if options.get("loop"):
        cmd.extend(
            [
                "--loop",
                "--max-iterations",
                str(int(options.get("max_iterations", 3))),
                "--completion-marker",
                str(options.get("completion_marker", "VERIFICATION_COMPLETE")),
                "--loop-foreground",
            ]
        )

    if options.get("worktree"):
        wt = prompt.get("worktree")
        if not isinstance(wt, dict):
            wt = _create_sprint_worktree(
                repo_root=repo_root,
                sprint_id=state.sprint_id,
                prompt_id=prompt_id,
                base_branch=str(options.get("base_branch", "main")),
            )
            prompt["worktree"] = wt

        worktree_path = Path(str(wt["path"]))
        task_file = worktree_path / "TASK.md"
        if not task_file.exists():
            _write_text_file(task_file, _read_text_file(prompt_path))

        cmd.extend(["--cwd", str(worktree_path), "--prompt-file", str(task_file), "--prompt-number", prompt_id])
    else:
        cmd.append(_prompt_ref_from_state_prompt(prompt))

    return cmd


def _interpret_executor_result(stdout: str, returncode: int) -> int:
    """Return 0 for success, non-zero for failure."""
    if returncode != 0:
        return returncode
    try:
        payload = json.loads(stdout)
    except Exception:
        # If we can't parse JSON, treat as failure to avoid false-success.
        return 2
    if not isinstance(payload, dict):
        return 2
    if payload.get("error"):
        return 2
    prompts = payload.get("prompts")
    if isinstance(prompts, list) and prompts:
        exec_info = (prompts[0] or {}).get("execution") or {}
        final_status = exec_info.get("final_status") or exec_info.get("status")
        if final_status and str(final_status).lower() not in {"completed"}:
            return 2
    return 0


def _run_executor_for_prompt(
    repo_root: Path,
    prompt: dict,
    model: str,
    options: dict,
    state: SprintState,
) -> int:
    executor = _executor_path(repo_root)
    if not executor.exists():
        raise RuntimeError("prompt-executor not found in repo; cannot auto-execute")

    prompt_id = str(prompt.get("id")).zfill(3)
    prompt_path = Path(str(prompt.get("path")))
    if not prompt_path.exists():
        raise RuntimeError(f"Prompt file missing for {prompt_id}: {prompt_path}")

    cmd = _build_executor_command(repo_root=repo_root, prompt=prompt, model=model, options=options, state=state)
    p = subprocess.run(cmd, cwd=repo_root, capture_output=True, text=True)
    if p.returncode != 0:
        # best-effort: print stderr for debugging
        sys.stderr.write(p.stderr)
        return p.returncode
    return _interpret_executor_result(p.stdout, p.returncode or 0)


def auto_execute(state: SprintState, options: dict, state_file: str = STATE_DEFAULT_FILE) -> None:
    """
    Execute the sprint automatically phase-by-phase.

    Notes:
    - Uses prompt-executor for execution.
    - For worktree mode, creates sprint-named worktrees and runs executor in that CWD.
    - Ctrl+C saves state (paused_at) and exits.
    """
    state.options = dict(options)
    state.options["auto_execute"] = True
    save_state(state, state_file)

    if not state.phases:
        cmd_replan(state_file)
        state = load_state(state_file) or state

    repo_root = get_repo_root()
    max_parallel = int(options.get("max_parallel", 5))

    try:
        phase_index = max(state.current_phase, 1)
        while phase_index <= len(state.phases):
            state.current_phase = phase_index
            save_state(state, state_file)

            phase = state.phases[phase_index - 1]
            runnable: list[dict] = []
            for pid in phase:
                p = _prompt_in_state(state, pid)
                if p.get("status") == "pending":
                    runnable.append(p)

            if not runnable:
                phase_index += 1
                continue

            # Check model availability before starting the phase and adjust if needed.
            availability = _cclimits_availability()
            if availability:
                models_list = [
                    m.strip()
                    for m in str(options.get("models", "claude,codex,gemini")).split(",")
                    if m.strip()
                ]
                for p in runnable:
                    model = p.get("model") or "codex"
                    if availability.get(model) is False:
                        for m in models_list:
                            if availability.get(m) is not False:
                                p["model"] = m
                                break
                save_state(state, state_file)

            print(f"== Phase {phase_index}/{len(state.phases)} ==")
            # Run in batches up to max_parallel
            for i in range(0, len(runnable), max_parallel):
                batch = runnable[i : i + max_parallel]
                for p in batch:
                    update_prompt_status(state, str(p.get("id")).zfill(3), "in_progress")
                save_state(state, state_file)

                # Prepare + launch all prompts in this batch in parallel.
                started_at: dict[str, float] = {}
                procs: list[tuple[dict, subprocess.Popen]] = []

                for p in batch:
                    pid = str(p.get("id")).zfill(3)
                    model = p.get("model") or "codex"
                    print(f"- Launching {pid} with {model}")
                    started_at[pid] = time.time()

                    # Ensure worktrees (if enabled) exist before launching.
                    if options.get("worktree") and not isinstance(p.get("worktree"), dict):
                        wt = _create_sprint_worktree(
                            repo_root=repo_root,
                            sprint_id=state.sprint_id,
                            prompt_id=pid,
                            base_branch=str(options.get("base_branch", "main")),
                        )
                        p["worktree"] = wt
                        worktree_path = Path(str(wt["path"]))
                        task_file = worktree_path / "TASK.md"
                        prompt_path = Path(str(p.get("path")))
                        _write_text_file(task_file, _read_text_file(prompt_path))

                    cmd = _build_executor_command(repo_root=repo_root, prompt=p, model=model, options=options, state=state)
                    proc = subprocess.Popen(cmd, cwd=repo_root, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                    procs.append((p, proc))

                print("")

                # Wait for completion
                for p, proc in procs:
                    pid = str(p.get("id")).zfill(3)
                    model = p.get("model") or "codex"
                    out, err = proc.communicate()

                    rc = proc.returncode or 0
                    if err:
                        # Keep stderr visible (best-effort) without failing parsing
                        sys.stderr.write(err)

                    final_rc = _interpret_executor_result(out, rc)
                    if final_rc == 0:
                        update_prompt_status(state, pid, "completed")
                    else:
                        update_prompt_status(state, pid, "failed")
                    save_state(state, state_file)

                    elapsed_min = int(max(1, (time.time() - started_at.get(pid, time.time())) / 60))
                    state.model_usage[model] = int(state.model_usage.get(model, 0)) + elapsed_min
                    save_state(state, state_file)

                if any(p.get("status") == "failed" for p in batch):
                    print("Failures detected. Fix issues then run:")
                    print(f"python3 skills/sprint/scripts/sprint.py resume --state-file {state_file}")
                    return

            phase_index += 1

        # Completed all phases
        state.current_phase = len(state.phases) + 1
        save_state(state, state_file)
        print("Sprint execution complete.")
    except KeyboardInterrupt:
        state.paused_at = _now_iso()
        save_state(state, state_file)
        print("\nInterrupted. State saved and sprint paused.")
        print(f"Resume: python3 skills/sprint/scripts/sprint.py resume --state-file {state_file}")


def _main_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Sprint planning + stateful execution")
    p.add_argument("spec", nargs="?", default=None, help="Spec file path or inline spec text")
    p.add_argument(
        "--from-existing",
        action="store_true",
        help="Analyze existing prompts instead of generating from spec (requires no spec argument)",
    )
    p.add_argument(
        "--prompts",
        type=str,
        help="Comma-separated prompt numbers/ranges to include (e.g., 001-005,010)",
    )
    p.add_argument(
        "--folder",
        type=str,
        help="Only include prompts from this subfolder of --output-dir",
    )
    p.add_argument(
        "--exclude",
        type=str,
        help="Comma-separated prompt numbers/ranges to exclude (e.g., 003,007)",
    )
    p.add_argument("--output-dir", default="./prompts/", help="Where to write prompt files (default: ./prompts/)")
    p.add_argument("--plan-file", default="./sprint-plan.md", help="Where to write the plan markdown")
    p.add_argument("--dry-run", action="store_true", help="Generate plan without creating prompt files/state")
    p.add_argument("--auto-execute", action="store_true", help="Execute sprint immediately, updating state")
    p.add_argument("--models", default="claude,codex,gemini", help="Comma-separated models")
    p.add_argument("--max-parallel", type=int, default=5, help="Max concurrent prompts per phase")
    p.add_argument("--worktree", action="store_true", help="Use worktrees during auto-execute")
    p.add_argument("--loop", action="store_true", help="Use verification loop during auto-execute")
    p.add_argument("--max-iterations", type=int, default=3, help="Max iterations for loop mode")
    p.add_argument("--completion-marker", default="VERIFICATION_COMPLETE", help="Loop completion marker")
    p.add_argument("--state-file", default=STATE_DEFAULT_FILE, help="State file path")
    p.add_argument("--json", action="store_true", help="Output JSON summary")
    return p


def _subcommand_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Sprint sub-commands")
    p.add_argument("subcommand", choices=sorted(SUBCOMMANDS))
    p.add_argument("args", nargs="*", help="Sub-command args")
    p.add_argument("--state-file", default=STATE_DEFAULT_FILE, help="State file path")
    p.add_argument("--yes", action="store_true", help="Skip confirmation (cancel)")
    return p


def _dispatch(argv: list[str]) -> int:
    if len(argv) >= 2 and argv[1] in SUBCOMMANDS:
        args = _subcommand_parser().parse_args(argv[1:])
        cmd = args.subcommand
        state_file = args.state_file

        if cmd == "status":
            cmd_status(state_file)
            return 0
        if cmd == "add":
            if not args.args:
                raise RuntimeError("Usage: sprint.py add \"<description>\"")
            cmd_add(" ".join(args.args).strip(), state_file)
            return 0
        if cmd == "remove":
            if not args.args:
                raise RuntimeError("Usage: sprint.py remove <prompt_id>")
            cmd_remove(args.args[0], state_file)
            return 0
        if cmd == "replan":
            cmd_replan(state_file)
            print("Replanned sprint.")
            return 0
        if cmd == "pause":
            cmd_pause(state_file)
            return 0
        if cmd == "resume":
            cmd_resume(state_file)
            return 0
        if cmd == "cancel":
            cmd_cancel(state_file, yes=args.yes)
            return 0
        if cmd == "history":
            cmd_history(".")
            return 0
        raise RuntimeError(f"Unknown subcommand: {cmd}")

    parser = _main_parser()
    args = parser.parse_args(argv[1:])

    if args.from_existing:
        if args.spec:
            parser.error("--from-existing cannot be used with a spec argument")
    else:
        if not args.spec:
            parser.error("spec is required unless --from-existing is provided")

    spec_content = ""
    spec_path = "from-existing" if args.from_existing else "inline"
    analysis: dict[str, Any] = {}
    if not args.from_existing:
        spec_content, spec_path = read_spec(str(args.spec))
        analysis = analyze_spec(spec_content)

    options = {
        "models": args.models,
        "max_parallel": args.max_parallel,
        "worktree": bool(args.worktree),
        "loop": bool(args.loop),
        "max_iterations": args.max_iterations,
        "completion_marker": args.completion_marker,
        "auto_execute": bool(args.auto_execute),
        "base_branch": "main",
    }

    models_list = [m.strip() for m in args.models.split(",") if m.strip()]

    if args.dry_run:
        # Plan only
        if args.from_existing:
            raw_prompts = discover_existing_prompts(
                Path(args.output_dir),
                include=args.prompts,
                folder=args.folder,
                exclude=args.exclude,
            )
            if not raw_prompts:
                raise RuntimeError(
                    "No prompts found for --from-existing under --output-dir."
                )
            prompts: list[dict] = []
            for rp in raw_prompts:
                pa = analyze_prompt_content(rp)
                stem = Path(str(rp.get("name") or "")).stem
                slug_part = stem.split("-", 1)[1] if "-" in stem else stem
                slug = _slugify(slug_part) if slug_part else _slugify(str(pa.get("title") or "prompt"))
                prompts.append(
                    {
                        "id": str(rp.get("ref") or rp.get("number") or "").strip(),
                        "number": str(rp.get("number") or "").zfill(3),
                        "title": pa.get("title") or stem,
                        "slug": slug,
                        "status": "pending",
                        "path": rp.get("path"),
                        "analysis": pa,
                    }
                )

            number_to_ids: dict[str, list[str]] = {}
            for p in prompts:
                number_to_ids.setdefault(str(p.get("number")), []).append(str(p.get("id")))

            file_to_producers: dict[str, set[str]] = {}
            for p in prompts:
                pa = p.get("analysis") or {}
                for f in (pa.get("output_files") or []):
                    file_to_producers.setdefault(str(f), set()).add(str(p.get("id")))

            prompt_deps: dict[str, list[str]] = {}
            for p in prompts:
                pa = p.get("analysis") or {}
                deps_ids: set[str] = set()
                for dep_num in (pa.get("dependencies") or []):
                    dep_num = str(dep_num).zfill(3)
                    matches = number_to_ids.get(dep_num) or []
                    if not matches:
                        continue
                    if len(matches) > 1:
                        sys.stderr.write(
                            f"WARNING: Ambiguous dependency '{dep_num}' referenced in {p.get('id')}: matches {matches}. "
                            "Skipping.\n"
                        )
                        continue
                    deps_ids.add(matches[0])
                for ref in (pa.get("referenced_files") or []):
                    for dep_id in file_to_producers.get(str(ref), set()):
                        if dep_id != str(p.get("id")):
                            deps_ids.add(dep_id)
                prompt_deps[str(p.get("id"))] = sorted(deps_ids)
                p["analysis"] = pa

            deps = build_dependency_graph(prompts, {"prompt_dependencies": prompt_deps})
            assignments = assign_models(prompts, models_list)
            created_at = _now_iso()
            hint = "existing-prompts"
            if args.folder:
                hint = f"existing-{_slugify(str(args.folder))}"
            sprint_id = _default_sprint_id(hint, "inline", created_at)
            plan_text, phases = generate_execution_plan(prompts, deps, assignments, options, sprint_id=sprint_id)
            print(plan_text)
            if args.json:
                print(
                    json.dumps(
                        {
                            "sprint_id": sprint_id,
                            "plan": plan_text,
                            "dependencies": deps,
                            "assignments": assignments,
                            "phases": phases,
                        },
                        indent=2,
                    )
                )
            return 0

        components = analysis.get("components", [])
        fake_prompts = []
        for i, c in enumerate(components, start=1):
            fake_prompts.append({"id": str(i).zfill(3), "title": c["title"], "slug": c["slug"], "status": "pending"})
        deps = build_dependency_graph(fake_prompts, analysis)
        assignments = assign_models(fake_prompts, models_list)
        sprint_id = _default_sprint_id(spec_content, spec_path, _now_iso())
        plan_text, _ = generate_execution_plan(fake_prompts, deps, assignments, options, sprint_id=sprint_id)
        print(plan_text)
        if args.json:
            print(json.dumps({"sprint_id": sprint_id, "plan": plan_text, "dependencies": deps, "assignments": assignments}, indent=2))
        return 0

    if args.from_existing:
        raw_prompts = discover_existing_prompts(
            Path(args.output_dir),
            include=args.prompts,
            folder=args.folder,
            exclude=args.exclude,
        )
        if not raw_prompts:
            raise RuntimeError(
                "No prompts found for --from-existing under --output-dir."
            )
        prompts = []
        for rp in raw_prompts:
            pa = analyze_prompt_content(rp)
            stem = Path(str(rp.get("name") or "")).stem
            slug_part = stem.split("-", 1)[1] if "-" in stem else stem
            slug = _slugify(slug_part) if slug_part else _slugify(str(pa.get("title") or "prompt"))
            prompts.append(
                {
                    "id": str(rp.get("ref") or rp.get("number") or "").strip(),
                    "number": str(rp.get("number") or "").zfill(3),
                    "status": "pending",
                    "worktree": None,
                    "merged": False,
                    "model": None,
                    "path": rp.get("path"),
                    "title": pa.get("title") or stem,
                    "slug": slug,
                    "analysis": pa,
                }
            )

        number_to_ids: dict[str, list[str]] = {}
        for p in prompts:
            number_to_ids.setdefault(str(p.get("number")), []).append(str(p.get("id")))

        file_to_producers: dict[str, set[str]] = {}
        for p in prompts:
            pa = p.get("analysis") or {}
            for f in (pa.get("output_files") or []):
                file_to_producers.setdefault(str(f), set()).add(str(p.get("id")))

        prompt_deps: dict[str, list[str]] = {}
        for p in prompts:
            pa = p.get("analysis") or {}
            deps_ids: set[str] = set()
            for dep_num in (pa.get("dependencies") or []):
                dep_num = str(dep_num).zfill(3)
                matches = number_to_ids.get(dep_num) or []
                if not matches:
                    continue
                if len(matches) > 1:
                    sys.stderr.write(
                        f"WARNING: Ambiguous dependency '{dep_num}' referenced in {p.get('id')}: matches {matches}. "
                        "Skipping.\n"
                    )
                    continue
                deps_ids.add(matches[0])
            for ref in (pa.get("referenced_files") or []):
                for dep_id in file_to_producers.get(str(ref), set()):
                    if dep_id != str(p.get("id")):
                        deps_ids.add(dep_id)
            prompt_deps[str(p.get("id"))] = sorted(deps_ids)
            p["analysis"] = pa

        deps = build_dependency_graph(prompts, {"prompt_dependencies": prompt_deps})
        assignments = assign_models(prompts, models_list)
    else:
        prompts = generate_prompts(analysis, args.output_dir)
        _resolve_prompt_paths(prompts, args.output_dir)
        deps = build_dependency_graph(prompts, analysis)
        assignments = assign_models(prompts, models_list)

    for p in prompts:
        pid = str(p.get("id")).zfill(3)
        p["model"] = assignments.get(pid, "codex")

    created_at = _now_iso()
    if args.from_existing:
        hint = "existing-prompts"
        if args.folder:
            hint = f"existing-{_slugify(str(args.folder))}"
        sprint_id = _default_sprint_id(hint, "inline", created_at)
    else:
        sprint_id = _default_sprint_id(spec_content, spec_path, created_at)
    plan_text, phases = generate_execution_plan(prompts, deps, assignments, options, sprint_id=sprint_id)
    _write_text_file(Path(args.plan_file), plan_text)
    _write_run_sprint_script(phases, assignments, options, output_path=Path("./run-sprint.sh"))

    state = SprintState(
        sprint_id=sprint_id,
        created_at=created_at,
        spec_hash=_sha256_hex(spec_content) if spec_content else "",
        spec_path=spec_path,
        prompts=[
            {k: v for k, v in p.items() if k in {"id", "status", "worktree", "merged", "model", "path", "title", "slug"}}
            for p in prompts
        ],
        current_phase=1,
        total_phases=len(phases),
        model_usage={},
        paused_at=None,
        output_dir=args.output_dir,
        plan_file=args.plan_file,
        phases=phases,
        dependencies=deps,
        options=options,
    )
    save_state(state, args.state_file)

    print(f"Created sprint state: {args.state_file}")
    print(f"Wrote plan: {args.plan_file}")
    print("Wrote run script: ./run-sprint.sh")
    print("")
    print(plan_text)

    if args.json:
        print(json.dumps({"state_file": args.state_file, "state": state.to_dict()}, indent=2))

    if args.auto_execute:
        auto_execute(state, options, state_file=args.state_file)

    return 0


def main() -> None:
    try:
        raise SystemExit(_dispatch(sys.argv))
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
