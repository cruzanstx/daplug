from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Optional

from .base import ConfigIssue, ModelInfo, SimpleCLIPlugin


class CodexCLI(SimpleCLIPlugin):
    _name = "codex"
    _display_name = "OpenAI Codex CLI"
    _executable_names = ["codex"]
    _version_cmd = ["codex", "--version"]
    _supported_providers = ["openai", "anthropic", "local"]
    _config_paths = [
        Path("~/.codex/config.toml"),
        Path("~/.codex/config.json"),
    ]

    def _pick_config_path(self) -> Optional[Path]:
        paths = self.get_config_paths()
        existing = [p for p in paths if p.exists()]
        if not existing:
            return None
        # Prefer JSON for patching if present.
        for p in existing:
            if p.suffix.lower() == ".json":
                return p
        return existing[0]

    def _has_allow_all_permissions(self, config: dict) -> bool:
        perms = config.get("permissions")
        return isinstance(perms, dict) and perms.get("*") == "allow"

    def detect_issues(self) -> list[ConfigIssue]:
        issues = super().detect_issues()
        installed, _exe = self.detect_installation()
        if not installed:
            return []

        config_path = self._pick_config_path()
        if config_path is None or not config_path.exists():
            return issues

        config = self.parse_config(config_path)
        if not isinstance(config, dict):
            return issues

        if not self._has_allow_all_permissions(config):
            issues.append(
                ConfigIssue(
                    type="sandbox_permissions",
                    severity="warning",
                    message="Sandbox permissions need adjustment",
                    fix_available=True,
                    fix_description=f'Add permissions {{ "*": "allow" }} to {config_path}',
                )
            )
        return issues

    def apply_fix(self, issue: ConfigIssue) -> bool:
        if issue.type != "sandbox_permissions":
            return False

        config_path = self._pick_config_path()
        if config_path is None:
            # Prefer creating the JSON config if nothing exists.
            for p in self.get_config_paths():
                if p.suffix.lower() == ".json":
                    config_path = p
                    break
        if config_path is None:
            return False

        config_path = config_path.expanduser()
        config_path.parent.mkdir(parents=True, exist_ok=True)

        backup_path = config_path.with_name(config_path.name + ".bak")
        try:
            original = (
                config_path.read_text(encoding="utf-8", errors="replace")
                if config_path.exists()
                else ""
            )
            backup_path.write_text(original, encoding="utf-8")
        except OSError:
            return False

        ok = False
        details: list[str] = []
        try:
            if config_path.suffix.lower() == ".json":
                raw: dict = {}
                if config_path.exists():
                    try:
                        raw = json.loads(config_path.read_text(encoding="utf-8", errors="replace"))
                    except json.JSONDecodeError:
                        raw = {}
                if not isinstance(raw, dict):
                    raw = {}
                perms = raw.get("permissions")
                if not isinstance(perms, dict):
                    perms = {}
                    raw["permissions"] = perms
                perms["*"] = "allow"
                config_path.write_text(json.dumps(raw, indent=2, sort_keys=True) + "\n", encoding="utf-8")
                ok = True
                details.append(f'✅ Added "permissions": {{"*": "allow"}}')
                details.append(f"📁 Backup saved to {backup_path}")
            else:
                # Best-effort TOML patching (no external deps).
                text = config_path.read_text(encoding="utf-8", errors="replace") if config_path.exists() else ""
                parsed = self.parse_config(config_path) if config_path.exists() else {}
                if isinstance(parsed, dict) and self._has_allow_all_permissions(parsed):
                    ok = True
                else:
                    lines = text.splitlines()
                    changed = False

                    # Inline table: permissions = { ... }
                    inline_re = re.compile(r'^(?P<prefix>\s*permissions\s*=\s*\{)(?P<body>.*?)(?P<suffix>\}\s*)$')
                    for i, line in enumerate(lines):
                        m = inline_re.match(line)
                        if not m:
                            continue
                        body = m.group("body").strip()
                        if '"*"' in body or "'*'" in body or "* =" in body:
                            break
                        if body:
                            if not body.endswith(","):
                                body += ","
                            body += ' "*" = "allow"'
                        else:
                            body = ' "*" = "allow"'
                        lines[i] = f'{m.group("prefix")}{body}{m.group("suffix")}'
                        changed = True
                        break

                    # Table form:
                    if not changed:
                        table_header_re = re.compile(r"^\s*\[permissions\]\s*$")
                        in_table = False
                        inserted = False
                        out: list[str] = []
                        for line in lines:
                            if table_header_re.match(line):
                                in_table = True
                                out.append(line)
                                continue
                            if in_table and line.strip().startswith("[") and line.strip().endswith("]"):
                                if not inserted:
                                    out.append('"*" = "allow"')
                                    inserted = True
                                in_table = False
                            out.append(line)
                        if in_table and not inserted:
                            out.append('"*" = "allow"')
                            inserted = True
                        if inserted:
                            lines = out
                            changed = True

                    if not changed:
                        if lines and lines[-1].strip() != "":
                            lines.append("")
                        lines.extend(["[permissions]", '"*" = "allow"'])

                    config_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
                    ok = True
                    details.append('✅ Added [permissions] "*" = "allow"')
                    details.append(f"📁 Backup saved to {backup_path}")
        except OSError:
            ok = False

        self._last_fix_info = {"details": "\n  ".join(details)}
        return ok

    def get_available_models(self) -> list[ModelInfo]:
        return [
            ModelInfo(
                id="openai:gpt-5.2-codex",
                display_name="GPT-5.2 Codex",
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


PLUGIN = CodexCLI()
