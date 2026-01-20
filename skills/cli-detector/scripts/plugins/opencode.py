from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Optional

from fixer import FIX_TEMPLATES, deep_merge_defaults, deep_merge_overwrite, load_template

from .base import ConfigIssue, ModelInfo, SimpleCLIPlugin, _strip_jsonc


class OpenCodeCLI(SimpleCLIPlugin):
    _name = "opencode"
    _display_name = "OpenCode"
    _executable_names = ["opencode"]
    _version_cmd = ["opencode", "--version"]
    _supported_providers = ["openai", "anthropic", "google", "zai", "local"]
    _config_paths = [
        Path("~/.config/opencode/opencode.json"),
        Path("opencode.json"),
    ]

    def get_available_models(self) -> list[ModelInfo]:
        return [
            ModelInfo(
                id="zai:glm-4.7",
                display_name="GLM-4.7 (via Z.AI)",
                provider="zai",
                capabilities=["code", "chat"],
            )
        ]

    def build_command(self, model: str, prompt_file: Path, cwd: Path) -> list[str]:
        _ = model, prompt_file, cwd
        # Conservative base command; prompt delivery depends on subcommand usage.
        return ["opencode", "--format", "json"]

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

    def _required_env_for_provider(self, provider: str) -> list[str]:
        provider = provider.strip().lower()
        if provider == "zai":
            return ["ZAI_KEY"]
        if provider == "openai":
            return ["OPENAI_API_KEY"]
        if provider == "anthropic":
            return ["ANTHROPIC_API_KEY"]
        if provider == "google":
            return ["GEMINI_API_KEY", "GOOGLE_API_KEY"]
        return []

    def detect_issues(self) -> list[ConfigIssue]:
        installed, _exe = self.detect_installation()
        if not installed:
            return []

        issues: list[ConfigIssue] = []
        active_path, config, parse_error = self._resolve_active_config()
        preferred_path = self.get_config_paths()[0] if self.get_config_paths() else Path("~/.config/opencode/opencode.json")

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
            provider_for_key_check = str(load_template("opencode").get("provider", "zai"))
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
            provider_for_key_check = "zai"
        else:
            provider_for_key_check = str((config or {}).get("provider", "zai"))

        required_envs = self._required_env_for_provider(provider_for_key_check)
        if required_envs and not any(os.environ.get(k) for k in required_envs):
            issues.append(
                ConfigIssue(
                    type="missing_api_key",
                    severity="error",
                    message=f"Missing API key env var for provider '{provider_for_key_check}': one of {required_envs}",
                    fix_available=False,
                )
            )

        if config is None:
            return issues

        perms = config.get("permission")
        if not isinstance(perms, dict) or perms.get("*") != "allow" or perms.get("external_directory") != "allow":
            issues.append(
                ConfigIssue(
                    type="sandbox_permissions",
                    severity="warning",
                    message='OpenCode permissions are missing or too restrictive (need "*" and "external_directory" = "allow")',
                    fix_available=True,
                    fix_description='Set "permission": {"*":"allow","external_directory":"allow"}',
                    config_path=str(active_path or preferred_path),
                )
            )

        required_keys = ["permission", "provider", "model", "mcpServers"]
        if any(k not in config for k in required_keys):
            issues.append(
                ConfigIssue(
                    type="outdated_config",
                    severity="warning",
                    message="OpenCode config missing recommended daplug defaults",
                    fix_available=True,
                    fix_description="Merge daplug defaults into existing config",
                    config_path=str(active_path or preferred_path),
                )
            )

        model = config.get("model")
        if not isinstance(model, str) or not model.strip():
            template = load_template("opencode")
            issues.append(
                ConfigIssue(
                    type="missing_model",
                    severity="warning",
                    message='OpenCode config missing "model"',
                    fix_available=True,
                    fix_description=f'Set model to "{template.get("model", "glm-4.7")}"',
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
        template = load_template("opencode")

        if issue.type in {"missing_config", "invalid_json"}:
            config_path.parent.mkdir(parents=True, exist_ok=True)
            config_path.write_text(json.dumps(template, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            return True

        try:
            raw = config_path.read_text(encoding="utf-8", errors="replace")
            existing = json.loads(_strip_jsonc(raw))
            existing_dict: dict[str, Any] = existing if isinstance(existing, dict) else {}
        except (OSError, json.JSONDecodeError):
            return False

        if issue.type == "sandbox_permissions":
            patch = (FIX_TEMPLATES.get("opencode") or {}).get("sandbox_permissions") or {}
            merged = deep_merge_overwrite(existing_dict, patch)
        elif issue.type == "outdated_config":
            merged = deep_merge_defaults(existing_dict, template)
        elif issue.type == "missing_model":
            merged = dict(existing_dict)
            merged["model"] = template.get("model", "glm-4.7")
        else:
            return False

        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(json.dumps(merged, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return True


PLUGIN = OpenCodeCLI()
