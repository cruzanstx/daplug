from __future__ import annotations

import json
import urllib.error
import urllib.request
from abc import ABC, abstractmethod
from dataclasses import dataclass
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
        """Default endpoint (e.g., 'http://localhost:1234')"""

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
