from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

from fixer import deep_merge_defaults, load_template

from .base import ConfigIssue, ModelInfo, SimpleCLIPlugin, _run_command, _strip_jsonc


class ClaudeCLI(SimpleCLIPlugin):
    _name = "claude"
    _display_name = "Claude Code"
    _executable_names = ["claude"]
    _version_cmd = ["claude", "--version"]
    _supported_providers = ["anthropic"]
    _config_paths = [
        Path("~/.claude/settings.json"),
        Path(".claude/settings.json"),
        Path(".claude/settings.local.json"),
    ]

    def get_available_models(self) -> list[ModelInfo]:
        # Keep this intentionally small; Claude model IDs are dynamic.
        return [
            ModelInfo(
                id="anthropic:claude",
                display_name="Claude (configured in Claude Code)",
                provider="anthropic",
                capabilities=["code", "chat"],
            )
        ]

    def build_command(self, model: str, prompt_file: Path, cwd: Path) -> list[str]:
        _ = model, prompt_file, cwd
        # Claude Code supports headless invocation, but daplug may choose to run it
        # interactively (PTY) depending on environment. Keep this conservative.
        return ["claude"]

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

        # Prefer first-party auth detection over env var checks. Claude Code can authenticate via
        # `claude auth login` (subscription plans), which does not require ANTHROPIC_API_KEY.
        auth_raw = _run_command(["claude", "auth", "status"], timeout_s=2.0)
        if auth_raw:
            try:
                auth = json.loads(auth_raw)
            except json.JSONDecodeError:
                auth = None
            if isinstance(auth, dict) and auth.get("loggedIn") is False:
                issues.append(
                    ConfigIssue(
                        type="auth",
                        severity="error",
                        message="Claude Code is not logged in (run `claude auth login`)",
                        fix_available=False,
                    )
                )
        else:
            # Non-fatal: don't block routing just because auth status couldn't be checked.
            issues.append(
                ConfigIssue(
                    type="auth_status_unknown",
                    severity="warning",
                    message="Unable to determine Claude Code auth status (claude auth status returned no output)",
                    fix_available=False,
                )
            )

        active_path, config, parse_error = self._resolve_active_config()
        preferred_path = self.get_config_paths()[0] if self.get_config_paths() else Path("~/.claude/settings.json")

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

        if config is None:
            return issues

        template = load_template("claude")
        required_allow = []
        perms = template.get("permissions") if isinstance(template, dict) else None
        if isinstance(perms, dict) and isinstance(perms.get("allow"), list):
            required_allow = [str(x) for x in perms.get("allow") if isinstance(x, str)]

        current_allow: list[str] = []
        cur_perms = config.get("permissions")
        if isinstance(cur_perms, dict) and isinstance(cur_perms.get("allow"), list):
            current_allow = [str(x) for x in cur_perms.get("allow") if isinstance(x, str)]

        if required_allow and not all(p in current_allow for p in required_allow):
            issues.append(
                ConfigIssue(
                    type="sandbox_permissions",
                    severity="warning",
                    message="Claude Code permissions missing required daplug allow entries",
                    fix_available=True,
                    fix_description="Add required Read/Write permissions for daplug",
                    config_path=str(active_path or preferred_path),
                )
            )

        if "model" not in config or "permissions" not in config:
            issues.append(
                ConfigIssue(
                    type="outdated_config",
                    severity="warning",
                    message="Claude Code config missing recommended daplug defaults",
                    fix_available=True,
                    fix_description="Merge daplug defaults into existing config",
                    config_path=str(active_path or preferred_path),
                )
            )

        model = config.get("model")
        if not isinstance(model, str) or not model.strip():
            issues.append(
                ConfigIssue(
                    type="missing_model",
                    severity="warning",
                    message='Claude Code config missing "model"',
                    fix_available=True,
                    fix_description=f'Set model to "{template.get("model", "claude")}"',
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
        template = load_template("claude")

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
            tmpl_perms = template.get("permissions") if isinstance(template, dict) else None
            required_allow: list[str] = []
            if isinstance(tmpl_perms, dict) and isinstance(tmpl_perms.get("allow"), list):
                required_allow = [str(x) for x in tmpl_perms.get("allow") if isinstance(x, str)]

            perms = existing_dict.get("permissions")
            if not isinstance(perms, dict):
                perms = {}
            allow = perms.get("allow")
            if not isinstance(allow, list):
                allow = []
            allow_str = [str(x) for x in allow if isinstance(x, str)]
            for entry in required_allow:
                if entry not in allow_str:
                    allow_str.append(entry)
            perms["allow"] = allow_str
            merged = dict(existing_dict)
            merged["permissions"] = perms
        elif issue.type == "outdated_config":
            merged = deep_merge_defaults(existing_dict, template if isinstance(template, dict) else {})
        elif issue.type == "missing_model":
            merged = dict(existing_dict)
            merged["model"] = template.get("model", "claude")
        else:
            return False

        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(json.dumps(merged, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return True


PLUGIN = ClaudeCLI()
