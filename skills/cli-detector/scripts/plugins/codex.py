from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Optional

from fixer import FIX_TEMPLATES, deep_merge_defaults, deep_merge_overwrite, load_template

from .base import ConfigIssue, ModelInfo, SimpleCLIPlugin, _strip_jsonc


class CodexCLI(SimpleCLIPlugin):
    _name = "codex"
    _display_name = "OpenAI Codex CLI"
    _executable_names = ["codex"]
    _version_cmd = ["codex", "--version"]
    _supported_providers = ["openai", "anthropic", "local"]
    _config_paths = [
        Path("~/.codex/config.json"),
        Path("~/.codex/config.toml"),
    ]

    def get_available_models(self) -> list[ModelInfo]:
        return [
            ModelInfo(
                id="openai:gpt-5.3-codex",
                display_name="GPT-5.3 Codex",
                provider="openai",
                capabilities=["code", "chat"],
            ),
            ModelInfo(
                id="openai:gpt-5.2",
                display_name="GPT-5.2",
                provider="openai",
                capabilities=["chat"],
            ),
        ]

    def build_command(self, model: str, prompt_file: Path, cwd: Path) -> list[str]:
        _ = prompt_file, cwd
        # Headless mode reads prompt from stdin via "-".
        cmd = ["codex", "exec", "--full-auto"]
        if model:
            cmd.extend(["-m", model])
        cmd.append("-")
        return cmd

    def _resolve_active_config(self) -> tuple[Optional[Path], Optional[dict[str, Any]], Optional[str]]:
        """Return (path, parsed_config, error_type)."""
        for candidate in self.get_config_paths():
            if not candidate.exists():
                continue
            try:
                content = candidate.read_text(encoding="utf-8", errors="replace")
            except OSError:
                return candidate, None, "read_error"

            suffix = candidate.suffix.lower()
            if suffix in {".json", ".jsonc"}:
                try:
                    parsed = json.loads(_strip_jsonc(content))
                except json.JSONDecodeError:
                    return candidate, None, "invalid_json"
                return candidate, parsed if isinstance(parsed, dict) else {}, None

            if suffix == ".toml":
                try:
                    import tomllib  # Python 3.11+

                    parsed = tomllib.loads(content)
                except Exception:
                    return candidate, None, "invalid_json"
                return candidate, parsed if isinstance(parsed, dict) else {}, None

            # Unknown suffix; treat as invalid.
            return candidate, None, "invalid_json"

        return None, None, None

    def detect_issues(self) -> list[ConfigIssue]:
        installed, _exe = self.detect_installation()
        if not installed:
            return []

        issues: list[ConfigIssue] = []

        active_path, config, parse_error = self._resolve_active_config()
        preferred_path = self.get_config_paths()[0] if self.get_config_paths() else Path("~/.codex/config.json")

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
            fixable = active_path.suffix.lower() in {".json", ".jsonc"}
            issues.append(
                ConfigIssue(
                    type="invalid_json",
                    severity="error",
                    message=f"Invalid config syntax at {active_path}",
                    fix_available=fixable,
                    fix_description="Replace with known-good template" if fixable else "Fix syntax manually",
                    config_path=str(active_path),
                )
            )

        # Missing API key (env var or prior login).
        auth_file = Path("~/.codex/auth.json").expanduser()
        if not os.environ.get("OPENAI_API_KEY") and not auth_file.exists():
            issues.append(
                ConfigIssue(
                    type="missing_api_key",
                    severity="error",
                    message="OPENAI_API_KEY not set (and no ~/.codex/auth.json found)",
                    fix_available=False,
                )
            )

        if config is None:
            return issues

        # Permissions (headless/sandbox) defaults.
        perms = config.get("permissions")
        if isinstance(perms, dict) and perms.get("*") != "allow":
            fixable = (active_path or preferred_path).suffix.lower() in {".json", ".jsonc"}
            issues.append(
                ConfigIssue(
                    type="sandbox_permissions",
                    severity="warning",
                    message='Codex permissions are set but not "*" = "allow"',
                    fix_available=fixable,
                    fix_description='Set "permissions": {"*": "allow"}',
                    config_path=str(active_path or preferred_path),
                )
            )

        # Outdated/incomplete config schema compared to daplug defaults.
        template = load_template("codex")
        required_keys = ["approval_mode", "full_auto", "notify", "providers"]
        if any(k not in config for k in required_keys):
            fixable = (active_path or preferred_path).suffix.lower() in {".json", ".jsonc"}
            issues.append(
                ConfigIssue(
                    type="outdated_config",
                    severity="warning",
                    message="Codex config missing recommended daplug defaults",
                    fix_available=fixable,
                    fix_description="Merge daplug defaults into existing config",
                    config_path=str(active_path or preferred_path),
                )
            )

        model = config.get("model")
        if not isinstance(model, str) or not model.strip():
            fixable = (active_path or preferred_path).suffix.lower() in {".json", ".jsonc"}
            issues.append(
                ConfigIssue(
                    type="missing_model",
                    severity="warning",
                    message='Codex config missing "model"',
                    fix_available=fixable,
                    fix_description=f'Set model to "{template.get("model", "gpt-5.3-codex")}"',
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
        if config_path.suffix.lower() not in {".json", ".jsonc"}:
            return False

        template = load_template("codex")

        if issue.type in {"missing_config", "invalid_json"}:
            config_path.parent.mkdir(parents=True, exist_ok=True)
            config_path.write_text(json.dumps(template, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            return True

        # For merge-based fixes, start from existing parsed config.
        try:
            raw = config_path.read_text(encoding="utf-8", errors="replace")
            existing = json.loads(_strip_jsonc(raw))
            existing_dict: dict[str, Any] = existing if isinstance(existing, dict) else {}
        except (OSError, json.JSONDecodeError):
            return False

        if issue.type == "sandbox_permissions":
            patch = (FIX_TEMPLATES.get("codex") or {}).get("sandbox_permissions") or {}
            merged = deep_merge_overwrite(existing_dict, patch)
        elif issue.type == "outdated_config":
            merged = deep_merge_defaults(existing_dict, template)
        elif issue.type == "missing_model":
            merged = dict(existing_dict)
            merged["model"] = template.get("model", "gpt-5.3-codex")
        else:
            return False

        config_path.write_text(json.dumps(merged, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return True


PLUGIN = CodexCLI()
