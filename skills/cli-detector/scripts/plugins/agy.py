from __future__ import annotations

import json
from pathlib import Path
from typing import cast

from .base import ConfigIssue, ModelInfo, SimpleCLIPlugin, _run_command, _strip_jsonc


_AGY_MODEL_ARGS = {
    "google:gemini-3-flash-preview": "Gemini 3.5 Flash (Medium)",
    "google:gemini-3.5-flash": "Gemini 3.5 Flash (Medium)",
    "google:gemini-2.5-flash": "Gemini 3.5 Flash (Medium)",
    "google:gemini-2.5-flash-lite": "Gemini 3.5 Flash (Low)",
    "google:gemini-2.5-pro": "Gemini 3.1 Pro (High)",
    "google:gemini-3-pro-preview": "Gemini 3.1 Pro (High)",
    "google:gemini-3.1-pro-preview": "Gemini 3.1 Pro (High)",
}


def _agy_model_arg(model: str) -> str:
    key = (model or "").strip()
    if not key:
        return "Gemini 3.5 Flash (Medium)"
    return _AGY_MODEL_ARGS.get(key, key)


class AgyCLI(SimpleCLIPlugin):
    _name: str = "agy"
    _display_name: str = "Google Antigravity CLI"
    _executable_names: list[str] = ["agy"]
    _version_cmd: list[str] = ["agy", "--version"]
    _supported_providers: list[str] = ["google"]
    _config_paths: list[Path] = [
        Path("~/.gemini/antigravity-cli/settings.json"),
        Path("~/.gemini/antigravity-cli/plugins"),
        Path("~/.gemini/config/mcp_config.json"),
        Path(".agents/mcp_config.json"),
        Path(".agents/skills"),
        Path("GEMINI.md"),
        Path("AGENTS.md"),
    ]

    def get_available_models(self) -> list[ModelInfo]:
        return [
            ModelInfo(
                id="google:gemini-3.5-flash",
                display_name="Gemini 3.5 Flash (Medium)",
                provider="google",
                capabilities=["code", "chat", "vision"],
            ),
            ModelInfo(
                id="google:gemini-3.1-pro-preview",
                display_name="Gemini 3.1 Pro (High)",
                provider="google",
                capabilities=["code", "chat", "vision"],
            ),
        ]

    def build_command(self, model: str, prompt_file: Path, cwd: Path) -> list[str]:
        _ = cwd
        prompt = prompt_file.read_text(encoding="utf-8", errors="replace")
        # agy --print requires the prompt as the flag value; stdin leaves --print without an argument.
        return ["agy", "--model", _agy_model_arg(model), "--print", prompt]

    def _resolve_active_config(self) -> tuple[Path | None, dict[str, object] | None, str | None]:
        for candidate in self.get_config_paths():
            if candidate.is_dir():
                continue
            if not candidate.exists():
                continue
            if candidate.suffix.lower() != ".json":
                return candidate, {}, None
            try:
                content = candidate.read_text(encoding="utf-8", errors="replace")
            except OSError:
                return candidate, None, "read_error"
            try:
                parsed = cast(object, json.loads(_strip_jsonc(content)))
            except json.JSONDecodeError:
                return candidate, None, "invalid_json"
            return candidate, cast(dict[str, object], parsed) if isinstance(parsed, dict) else {}, None
        return None, None, None

    def detect_issues(self) -> list[ConfigIssue]:
        installed, _exe = self.detect_installation()
        if not installed:
            return []

        issues: list[ConfigIssue] = []
        active_path, _config, parse_error = self._resolve_active_config()
        preferred_path = self.get_config_paths()[0]

        help_text = _run_command(["agy", "--help"])
        if help_text and ("--model" not in help_text or "--print" not in help_text):
            issues.append(
                ConfigIssue(
                    type="unsupported_command_flags",
                    severity="error",
                    message="Installed agy does not advertise the --model/--print flags required for noninteractive daplug runs",
                    fix_available=False,
                )
            )

        if active_path is None:
            issues.append(
                ConfigIssue(
                    type="missing_config",
                    severity="info",
                    message="No Antigravity settings found; agy may create them after login or first run",
                    fix_available=False,
                    config_path=str(preferred_path),
                )
            )
        elif parse_error == "invalid_json":
            issues.append(
                ConfigIssue(
                    type="invalid_json",
                    severity="error",
                    message=f"Invalid Antigravity config syntax at {active_path}",
                    fix_available=False,
                    config_path=str(active_path),
                )
            )
        elif parse_error == "read_error":
            issues.append(
                ConfigIssue(
                    type="read_error",
                    severity="warning",
                    message=f"Could not read Antigravity config at {active_path}",
                    fix_available=False,
                    config_path=str(active_path),
                )
            )

        return issues

    def apply_fix(self, issue: ConfigIssue) -> bool:
        _ = issue
        return False


PLUGIN = AgyCLI()
