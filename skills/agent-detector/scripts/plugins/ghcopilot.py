from __future__ import annotations

from pathlib import Path
from typing import Optional

from .base import ConfigIssue, ModelInfo, SimpleCLIPlugin, _run_command


class GHCopilotCLI(SimpleCLIPlugin):
    _name = "ghcopilot"
    _display_name = "GitHub Copilot CLI (gh extension)"
    _executable_names = ["gh"]
    _version_cmd = ["gh", "copilot", "--version"]
    _supported_providers = ["github"]
    _config_paths = [
        Path("~/.config/github-copilot/"),
    ]

    def _resolve_gh(self) -> Optional[str]:
        installed, exe = super().detect_installation()
        return exe if installed else None

    def detect_installation(self) -> tuple[bool, Optional[str]]:
        gh = self._resolve_gh()
        if not gh:
            self._cached_executable = None
            return False, None

        out = _run_command([gh, "extension", "list"]) or ""
        if "github/gh-copilot" not in out:
            self._cached_executable = None
            return False, None

        self._cached_executable = gh
        return True, gh

    def detect_issues(self) -> list[ConfigIssue]:
        gh = self._resolve_gh()
        if not gh:
            return []

        ext_list = _run_command([gh, "extension", "list"]) or ""
        if "github/gh-copilot" not in ext_list:
            return [
                ConfigIssue(
                    type="missing_extension",
                    severity="info",
                    message="GitHub Copilot CLI extension not installed (run: gh extension install github/gh-copilot)",
                    fix_available=False,
                )
            ]

        auth = _run_command([gh, "auth", "status"]) or ""
        if ("Logged in" not in auth) and ("Logged in to" not in auth):
            return [
                ConfigIssue(
                    type="missing_auth",
                    severity="warning",
                    message="GitHub CLI not authenticated (run: gh auth login)",
                    fix_available=False,
                )
            ]

        return []

    def get_available_models(self) -> list[ModelInfo]:
        return [
            ModelInfo(
                id="github:copilot",
                display_name="GitHub Copilot (suggest/explain)",
                provider="github",
                capabilities=["suggest", "explain"],
            )
        ]

    def build_command(self, model: str, prompt_file: Path, cwd: Path) -> list[str]:
        _ = model, prompt_file, cwd
        # This is not a general-purpose prompt runner; suggest is the most useful default.
        return ["gh", "copilot", "suggest"]


PLUGIN = GHCopilotCLI()

