from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from typing import Optional


@dataclass
class ProviderStatus:
    running: bool
    endpoint: str
    loaded_models: list[str]
    compatible_clis: list[str]


class ProviderPlugin(ABC):
    """Base class for local model provider detection plugins."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Internal name (e.g., 'lmstudio')"""

    @property
    @abstractmethod
    def display_name(self) -> str:
        """Human-readable name"""

    @property
    @abstractmethod
    def default_endpoint(self) -> str:
        """Default base URL (e.g., 'http://localhost:1234/v1')"""

    @abstractmethod
    def detect_running(self, timeout_s: float = 0.3) -> tuple[bool, str]:
        """Returns (running, endpoint)"""

    @abstractmethod
    def list_models(self, endpoint: str, timeout_s: float = 0.5) -> list[str]:
        """Return list of available/loaded models for endpoint."""

    @abstractmethod
    def compatible_clis(self) -> list[str]:
        """Return list of CLIs that can use this provider."""


def http_get_json(url: str, timeout_s: float) -> Optional[dict]:
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            data = resp.read()
    except (urllib.error.URLError, ValueError):
        return None
    try:
        return json.loads(data.decode("utf-8", errors="replace"))
    except json.JSONDecodeError:
        return None


CONFIG_OPEN = "<daplug_config>"
CONFIG_CLOSE = "</daplug_config>"


def _find_project_claude_md(start: Optional[Path] = None) -> Optional[Path]:
    start = start or Path.cwd()
    for candidate_dir in [start, *start.parents]:
        path = candidate_dir / "CLAUDE.md"
        if path.exists():
            return path
    return None


def _extract_blocks(content: str) -> list[str]:
    blocks: list[str] = []
    idx = 0
    while True:
        start = content.find(CONFIG_OPEN, idx)
        if start == -1:
            break
        end = content.find(CONFIG_CLOSE, start)
        if end == -1:
            blocks.append(content[start + len(CONFIG_OPEN) :])
            break
        blocks.append(content[start + len(CONFIG_OPEN) : end])
        idx = end + len(CONFIG_CLOSE)
    return blocks


def _parse_block(block: str) -> dict[str, Any]:
    data: dict[str, Any] = {}
    lines = block.splitlines()
    i = 0
    while i < len(lines):
        raw = lines[i].rstrip("\n")
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            i += 1
            continue
        if ":" not in stripped:
            i += 1
            continue
        key, value = stripped.split(":", 1)
        key = key.strip()
        value = value.strip()

        if key == "local_providers":
            providers: dict[str, str] = {}

            # Optional single-line JSON representation:
            # local_providers: {"lmstudio":"http://.../v1"}
            if value:
                try:
                    parsed = json.loads(value)
                    if isinstance(parsed, dict):
                        providers = {str(k): str(v) for k, v in parsed.items() if v}
                except json.JSONDecodeError:
                    providers = {}

            i += 1
            # Parse indented YAML-ish child lines:
            #   lmstudio: http://host:1234/v1
            while i < len(lines):
                child_raw = lines[i]
                if not child_raw.strip():
                    i += 1
                    continue
                if child_raw.lstrip() == child_raw:
                    break
                child = child_raw.strip()
                if child.startswith("#") or ":" not in child:
                    i += 1
                    continue
                c_key, c_val = child.split(":", 1)
                c_key = c_key.strip()
                c_val = c_val.strip()
                if c_key and c_val:
                    providers[c_key] = c_val
                i += 1

            if providers:
                data["local_providers"] = providers
            continue

        data[key] = value
        i += 1
    return data


def _load_config_from_path(path: Path) -> dict[str, Any]:
    try:
        content = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return {}

    combined: dict[str, Any] = {}
    for block in _extract_blocks(content):
        combined.update(_parse_block(block))
    return combined


def load_daplug_config() -> dict[str, Any]:
    """
    Load <daplug_config> with project-over-user precedence.

    Note: We only parse what's needed for provider endpoint discovery (especially
    the YAML-ish `local_providers:` mapping). This is intentionally independent
    of config-reader for robustness when running as a standalone helper.
    """
    user_path = Path.home() / ".claude" / "CLAUDE.md"
    project_path = _find_project_claude_md()

    user_cfg = _load_config_from_path(user_path) if user_path.exists() else {}
    project_cfg = _load_config_from_path(project_path) if project_path and project_path.exists() else {}

    merged: dict[str, Any] = dict(user_cfg)
    merged.update(project_cfg)

    # Deep-merge local_providers (project overrides user keys).
    lp: dict[str, str] = {}
    if isinstance(user_cfg.get("local_providers"), dict):
        lp.update({str(k): str(v) for k, v in user_cfg["local_providers"].items() if v})
    if isinstance(project_cfg.get("local_providers"), dict):
        lp.update({str(k): str(v) for k, v in project_cfg["local_providers"].items() if v})
    if lp:
        merged["local_providers"] = lp

    return merged


def get_provider_endpoint(provider: str, config: Optional[dict[str, Any]] = None) -> Optional[str]:
    """Get endpoint for provider, checking config → env → default."""
    cfg = config or load_daplug_config()
    local_providers = cfg.get("local_providers") if isinstance(cfg, dict) else None
    if not isinstance(local_providers, dict):
        local_providers = {}

    name = (provider or "").strip().lower()
    if name == "lmstudio":
        return (
            str(local_providers.get("lmstudio") or "").strip()
            or os.environ.get("LMSTUDIO_ENDPOINT")
            or "http://localhost:1234/v1"
        )
    if name == "ollama":
        return (
            str(local_providers.get("ollama") or "").strip()
            or os.environ.get("OLLAMA_HOST")
            or "http://localhost:11434/v1"
        )
    if name == "vllm":
        return (
            str(local_providers.get("vllm") or "").strip()
            or os.environ.get("VLLM_ENDPOINT")
            or "http://localhost:8000/v1"
        )
    return None


def join_url(base: str, suffix: str) -> str:
    base = (base or "").rstrip("/")
    suffix = (suffix or "").lstrip("/")
    return f"{base}/{suffix}" if base else f"/{suffix}"


def strip_v1(base_url: str) -> str:
    """Convert an OpenAI base URL (.../v1) to a root URL suitable for non-v1 endpoints."""
    url = (base_url or "").rstrip("/")
    if url.endswith("/v1"):
        return url[: -len("/v1")]
    return url
