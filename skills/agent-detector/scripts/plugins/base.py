from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

try:
    import tomllib  # Python 3.11+
except ModuleNotFoundError:  # pragma: no cover
    tomllib = None  # type: ignore[assignment]


@dataclass
class ModelInfo:
    id: str
    display_name: str
    provider: str
    capabilities: list[str] = None  # e.g., ["code", "chat", "vision"]


@dataclass
class ConfigIssue:
    type: str  # e.g., "sandbox_permissions", "missing_api_key"
    severity: str  # "error", "warning", "info"
    message: str
    fix_available: bool
    fix_description: Optional[str] = None


class CLIPlugin(ABC):
    """Base class for CLI detection plugins."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Internal name (e.g., 'codex')"""

    @property
    @abstractmethod
    def display_name(self) -> str:
        """Human-readable name (e.g., 'OpenAI Codex CLI')"""

    @property
    @abstractmethod
    def executable_names(self) -> list[str]:
        """Possible executable names to search for"""

    @abstractmethod
    def detect_installation(self) -> tuple[bool, Optional[str]]:
        """Returns (is_installed, executable_path)"""

    @abstractmethod
    def get_version(self) -> Optional[str]:
        """Get installed version"""

    @abstractmethod
    def get_config_paths(self) -> list[Path]:
        """Return possible config file locations"""

    @abstractmethod
    def parse_config(self, config_path: Path) -> dict:
        """Parse config file and return normalized dict"""

    @abstractmethod
    def get_available_models(self) -> list[ModelInfo]:
        """Return models available through this CLI"""

    @abstractmethod
    def get_supported_providers(self) -> list[str]:
        """Return providers this CLI can connect to"""

    @abstractmethod
    def detect_issues(self) -> list[ConfigIssue]:
        """Detect configuration issues"""

    @abstractmethod
    def apply_fix(self, issue: ConfigIssue) -> bool:
        """Attempt to fix an issue. Returns success."""

    @abstractmethod
    def build_command(self, model: str, prompt_file: Path, cwd: Path) -> list[str]:
        """Build CLI command to run a prompt"""


def _strip_jsonc(text: str) -> str:
    # Minimal JSON-with-comments stripping for common cases.
    text = re.sub(r"(?m)^\\s*//.*$", "", text)
    text = re.sub(r"(?m)^\\s*#.*$", "", text)
    text = re.sub(r"/\\*.*?\\*/", "", text, flags=re.DOTALL)
    return text


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def _run_command(cmd: list[str], cwd: Optional[Path] = None, timeout_s: float = 2.0) -> Optional[str]:
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=False,
            cwd=str(cwd) if cwd else None,
            timeout=timeout_s,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    out = (result.stdout or "").strip()
    err = (result.stderr or "").strip()
    return out or err or None


class SimpleCLIPlugin(CLIPlugin):
    """Small helper base class for common CLI detection behavior.

    Subclasses typically only set the class attributes and implement build_command().
    """

    _name: str = ""
    _display_name: str = ""
    _executable_names: list[str] = []
    _version_cmd: list[str] = []
    _config_paths: list[Path] = []
    _supported_providers: list[str] = []

    def __init__(self) -> None:
        self._cached_executable: Optional[str] = None

    @property
    def name(self) -> str:  # type: ignore[override]
        return self._name

    @property
    def display_name(self) -> str:  # type: ignore[override]
        return self._display_name

    @property
    def executable_names(self) -> list[str]:  # type: ignore[override]
        return list(self._executable_names)

    @property
    def version_cmd(self) -> list[str]:
        return list(self._version_cmd) if self._version_cmd else [self.executable_names[0], "--version"]

    def detect_installation(self) -> tuple[bool, Optional[str]]:
        for exe in self.executable_names:
            resolved = shutil.which(exe)
            if resolved:
                self._cached_executable = resolved
                return True, resolved
        self._cached_executable = None
        return False, None

    def get_version(self) -> Optional[str]:
        installed, exe_path = self.detect_installation()
        if not installed:
            return None
        cmd = self.version_cmd
        if exe_path:
            cmd = [exe_path, *cmd[1:]]
        return _run_command(cmd)

    def get_config_paths(self) -> list[Path]:
        expanded: list[Path] = []
        for path in self._config_paths:
            raw = os.path.expandvars(str(path))
            expanded.append(Path(raw).expanduser())
        return expanded

    def parse_config(self, config_path: Path) -> dict:
        try:
            content = _read_text(config_path)
        except OSError:
            return {}

        suffix = config_path.suffix.lower()
        if suffix in (".json", ".jsonc"):
            try:
                return json.loads(_strip_jsonc(content))
            except json.JSONDecodeError:
                return {}
        if suffix == ".toml":
            if tomllib is None:
                return {}
            try:
                return tomllib.loads(content)
            except Exception:
                return {}

        # Best-effort fallback: try JSON then TOML.
        try:
            return json.loads(_strip_jsonc(content))
        except json.JSONDecodeError:
            pass
        if tomllib is None:
            return {}
        try:
            return tomllib.loads(content)
        except Exception:
            return {}

    def get_supported_providers(self) -> list[str]:
        return list(self._supported_providers)

    def get_available_models(self) -> list[ModelInfo]:
        return []

    def detect_issues(self) -> list[ConfigIssue]:
        installed, _exe = self.detect_installation()
        if not installed:
            return []
        existing = [p for p in self.get_config_paths() if p.exists()]
        if existing:
            return []
        return [
            ConfigIssue(
                type="missing_config",
                severity="info",
                message=f"No config found for {self.display_name}",
                fix_available=False,
            )
        ]

    def apply_fix(self, issue: ConfigIssue) -> bool:
        _ = issue
        return False


def modelinfo_to_dict(model: ModelInfo) -> dict[str, Any]:
    data: dict[str, Any] = {
        "id": model.id,
        "display_name": model.display_name,
        "provider": model.provider,
    }
    if model.capabilities is not None:
        data["capabilities"] = list(model.capabilities)
    return data


def configissue_to_dict(issue: ConfigIssue) -> dict[str, Any]:
    data: dict[str, Any] = {
        "type": issue.type,
        "severity": issue.severity,
        "message": issue.message,
        "fix_available": issue.fix_available,
    }
    if issue.fix_description is not None:
        data["fix_description"] = issue.fix_description
    return data
