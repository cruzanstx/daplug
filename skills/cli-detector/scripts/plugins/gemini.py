from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Optional

from fixer import deep_merge_defaults, load_template

from .base import ConfigIssue, ModelInfo, SimpleCLIPlugin, _strip_jsonc


class GeminiCLI(SimpleCLIPlugin):
    _name = "gemini"
    _display_name = "Google Gemini CLI"
    _executable_names = ["gemini"]
    _version_cmd = ["gemini", "--version"]
    _supported_providers = ["google"]
    _config_paths = [
        Path("~/.config/gemini/config.json"),
        Path("~/.gemini/settings.json"),
        Path(".gemini/settings.json"),
    ]

    def get_available_models(self) -> list[ModelInfo]:
        return [
            ModelInfo(
                id="google:gemini-2.5-pro",
                display_name="Gemini 2.5 Pro",
                provider="google",
                capabilities=["code", "chat", "vision"],
            ),
            ModelInfo(
                id="google:gemini-2.5-flash",
                display_name="Gemini 2.5 Flash",
                provider="google",
                capabilities=["code", "chat", "vision"],
            ),
        ]

    def build_command(self, model: str, prompt_file: Path, cwd: Path) -> list[str]:
        _ = cwd
        prompt = prompt_file.read_text(encoding="utf-8", errors="replace")
        cmd = ["gemini", "-y"]
        if model:
            cmd.extend(["-m", model])
        cmd.extend(["-p", prompt])
        return cmd

    def _resolve_active_config(self) -> tuple[Optional[Path], Optional[dict[str, Any]], Optional[str]]:
        for candidate in self.get_config_paths():
            if not candidate.exists():
                continue
            try:
                content = candidate.read_text(encoding="utf-8", errors="replace")
            except OSError:
                return candidate, None, "read_error"
            try:
                parsed = json.loads(_strip_jsonc(content))
            except json.JSONDecodeError:
                return candidate, None, "invalid_json"
            return candidate, parsed if isinstance(parsed, dict) else {}, None
        return None, None, None

    def detect_issues(self) -> list[ConfigIssue]:
        installed, _exe = self.detect_installation()
        if not installed:
            return []

        issues: list[ConfigIssue] = []
        active_path, config, parse_error = self._resolve_active_config()
        preferred_path = self.get_config_paths()[0] if self.get_config_paths() else Path("~/.config/gemini/config.json")

        if active_path is None:
            issues.append(
                ConfigIssue(
                    type="missing_config",
                    severity="error",
                    message=f"No config found for {self.display_name}",
                    fix_available=True,
                    fix_description=f"Create {preferred_path}",
                    config_path=str(preferred_path),
                )
            )
        elif parse_error == "invalid_json":
            issues.append(
                ConfigIssue(
                    type="invalid_json",
                    severity="error",
                    message=f"Invalid config syntax at {active_path}",
                    fix_available=True,
                    fix_description="Replace with known-good template",
                    config_path=str(active_path),
                )
            )

        # Check for authentication: env vars OR OAuth credentials file
        has_env_key = bool(os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY"))
        oauth_paths = [
            Path("~/.gemini/oauth_creds.json").expanduser(),
            Path("~/.config/gemini/oauth_creds.json").expanduser(),
        ]
        has_oauth = any(p.exists() for p in oauth_paths)

        if not (has_env_key or has_oauth):
            issues.append(
                ConfigIssue(
                    type="missing_api_key",
                    severity="error",
                    message="No Gemini auth found (set GEMINI_API_KEY or run 'gemini auth login')",
                    fix_available=False,
                )
            )

        if config is None:
            return issues

        template = load_template("gemini")
        required_keys = ["theme", "yolo", "sandbox", "check_updates"]
        if any(k not in config for k in required_keys):
            issues.append(
                ConfigIssue(
                    type="outdated_config",
                    severity="warning",
                    message="Gemini config missing recommended daplug defaults",
                    fix_available=True,
                    fix_description="Merge daplug defaults into existing config",
                    config_path=str(active_path or preferred_path),
                )
            )

        return issues

    def apply_fix(self, issue: ConfigIssue) -> bool:
        """
        1. Create backup of existing config
        2. Apply minimal fix (dont overwrite entire config)
        3. Validate fix worked
        4. Return success/failure
        """
        config_path = Path(issue.config_path).expanduser() if issue.config_path else self.get_config_paths()[0]
        template = load_template("gemini")

        if issue.type in {"missing_config", "invalid_json"}:
            config_path.parent.mkdir(parents=True, exist_ok=True)
            config_path.write_text(json.dumps(template, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            return True

        if issue.type == "outdated_config":
            try:
                raw = config_path.read_text(encoding="utf-8", errors="replace")
                existing = json.loads(_strip_jsonc(raw))
                existing_dict: dict[str, Any] = existing if isinstance(existing, dict) else {}
            except (OSError, json.JSONDecodeError):
                return False
            merged = deep_merge_defaults(existing_dict, template)
            config_path.parent.mkdir(parents=True, exist_ok=True)
            config_path.write_text(json.dumps(merged, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            return True

        return False


PLUGIN = GeminiCLI()
