"""No-Google policy guard for protected repositories.

Owner policy: TLDRHQ / youtubesummaries source code is never sent to Google.
This ports the check from the ``~/.local/bin/daplug-run`` wrapper into the
executor, so direct ``executor.py`` invocations (and Antigravity-driven daplug
runs that never touch the wrapper) are covered too.

* Protected repos: the repo root path, any explicit execution directory, or
  their git ``origin`` URL matches ``DAPLUG_NO_GOOGLE_REPOS`` (default
  ``tldrhq|youtube[_-]?summaries``, matched case-insensitively).
  ``DAPLUG_NO_GOOGLE_REPOS=''`` deliberately disables the guard.
* Google routes: any registry model with ``routing.google == true`` or
  ``default_cli`` in {agy, gemini}, plus an explicit ``--cli agy|gemini``
  (aliases normalized). After CLI resolution, a router-selected agy/gemini CLI
  is refused as well.
* Fail closed: refuse and never substitute a model silently.
"""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path
from typing import Iterable, Mapping, Optional, Sequence

NO_GOOGLE_ENV = "DAPLUG_NO_GOOGLE_REPOS"
DEFAULT_NO_GOOGLE_REPOS = r"tldrhq|youtube[_-]?summaries"
GOOGLE_CLIS = frozenset({"agy", "gemini"})
_CLI_ALIASES = {"antigravity": "agy"}
REFUSAL_EXIT_CODE = 2

SUGGESTED_ROUTES = "codex | sol | terra | glm53 | syn-glm53-flash | syn-ds41-flash | local"


class GoogleRouteRefused(RuntimeError):
    """Raised when a Google route is requested inside a protected repo."""


def _normalize_cli(cli: Optional[str]) -> Optional[str]:
    value = (cli or "").strip().lower()
    if not value:
        return None
    return _CLI_ALIASES.get(value, value)


def protected_repo_pattern(env: Optional[Mapping[str, str]] = None) -> Optional[str]:
    """Return the active protected-repo regex, or None when the guard is disabled.

    Unset uses the default; an explicitly empty value disables the guard.
    """
    environ = os.environ if env is None else env
    raw = environ.get(NO_GOOGLE_ENV)
    if raw is None:
        return DEFAULT_NO_GOOGLE_REPOS
    if raw.strip() == "":
        return None
    return raw


def _git_origin_url(path: Path) -> Optional[str]:
    try:
        result = subprocess.run(
            ["git", "-C", str(path), "remote", "get-url", "origin"],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    return result.stdout.strip() or None


def find_protected_match(
    paths: Iterable[Optional[os.PathLike | str]],
    pattern: str,
) -> Optional[str]:
    """Return a human-readable reason if any path or its origin URL matches."""
    try:
        regex = re.compile(pattern, re.IGNORECASE)
    except re.error as exc:
        # Cannot evaluate the policy: treat every repo as protected.
        return f"{NO_GOOGLE_ENV} is not a valid regex ({exc}); failing closed"

    candidates: list[Path] = []
    for raw in paths:
        if not raw:
            continue
        path = Path(raw)
        if path not in candidates:
            candidates.append(path)

    for path in candidates:
        if regex.search(str(path)):
            return f"repo path {path}"
    for path in candidates:
        if not path.is_dir():
            continue
        origin = _git_origin_url(path)
        if origin and regex.search(origin):
            return f"origin URL {origin} (repo {path})"
    return None


def google_route_reason(
    model: str,
    cli: Optional[str],
    registry_by_name: Mapping[str, Mapping],
) -> Optional[str]:
    """Return why (model, cli) is a Google route, or None if it is not."""
    cli = _normalize_cli(cli)
    if cli in GOOGLE_CLIS:
        return f"--cli {cli} runs through a Google CLI"
    entry = registry_by_name.get(model)
    if entry is None:
        return f"model '{model}' is not in the daplug registry; refusing to guess whether it routes through Google"
    routing = entry.get("routing") or {}
    if routing.get("google"):
        return f"model '{model}' has routing.google=true"
    default_cli = entry.get("default_cli")
    if default_cli in GOOGLE_CLIS:
        return f"model '{model}' runs through the {default_cli} CLI by default"
    return None


def _refusal_message(repo_reason: str, route: str, model: str, cli: Optional[str]) -> str:
    return (
        "daplug executor: REFUSED - Google route blocked in a protected repo.\n"
        f"  protected: {repo_reason}\n"
        f"  model:     {model or '(unset)'}\n"
        f"  cli:       {cli or '(unset)'}\n"
        f"  reason:    {route}\n"
        "Policy: TLDRHQ / youtubesummaries source code is never sent to Google, "
        "including agy, gemini, and Claude models run through the Antigravity CLI.\n"
        f"Pick a non-Google route, e.g. --model {SUGGESTED_ROUTES}\n"
        f"Deliberate bypass: {NO_GOOGLE_ENV}='' executor.py ..."
    )


def enforce_no_google_policy(
    routes: Sequence[tuple[str, Optional[str]]],
    paths: Iterable[Optional[os.PathLike | str]],
    registry_by_name: Mapping[str, Mapping],
    env: Optional[Mapping[str, str]] = None,
) -> None:
    """Raise GoogleRouteRefused if any requested route is Google in a protected repo.

    ``routes`` holds (model, cli_override) pairs: one for --model runs, one per
    --moa entry. Call this before any worktree, log, or CLI preflight is created.
    """
    pattern = protected_repo_pattern(env)
    if pattern is None:
        return
    offending = [
        (model, cli, reason)
        for model, cli in routes
        if (reason := google_route_reason(model, cli, registry_by_name))
    ]
    if not offending:
        return
    repo_reason = find_protected_match(paths, pattern)
    if repo_reason is None:
        return
    model, cli, reason = offending[0]
    raise GoogleRouteRefused(_refusal_message(repo_reason, reason, model, cli))


def enforce_resolved_cli_policy(
    resolved: Sequence[tuple[str, Optional[str]]],
    paths: Iterable[Optional[os.PathLike | str]],
    env: Optional[Mapping[str, str]] = None,
) -> None:
    """Second check after CLI resolution: refuse a router-selected agy/gemini CLI.

    ``resolved`` holds (model, selected_cli) pairs from get_cli_info().
    """
    pattern = protected_repo_pattern(env)
    if pattern is None:
        return
    offending = [(model, cli) for model, cli in resolved if _normalize_cli(cli) in GOOGLE_CLIS]
    if not offending:
        return
    repo_reason = find_protected_match(paths, pattern)
    if repo_reason is None:
        return
    model, cli = offending[0]
    raise GoogleRouteRefused(
        _refusal_message(repo_reason, f"CLI routing resolved '{model}' to the {cli} CLI", model, cli)
    )
