from __future__ import annotations

import re
from pathlib import Path

from .base import ModelInfo, SimpleCLIPlugin

try:
    import yaml  # type: ignore
except ModuleNotFoundError:  # pragma: no cover
    yaml = None


def _parse_env(content: str) -> dict:
    data: dict[str, str] = {}
    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key:
            continue
        # Strip optional surrounding quotes.
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        # Handle common "export KEY=VALUE" syntax.
        key = re.sub(r"^export\\s+", "", key)
        data[key] = value
    return data


class AiderCLI(SimpleCLIPlugin):
    _name = "aider"
    _display_name = "Aider"
    _executable_names = ["aider"]
    _version_cmd = ["aider", "--version"]
    _supported_providers = ["openai", "anthropic", "google", "ollama", "openrouter"]
    _config_paths = [
        Path(".aider.conf.yml"),
        Path("~/.aider.conf.yml"),
        Path(".env"),
    ]

    def parse_config(self, config_path: Path) -> dict:
        try:
            content = config_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return {}

        if config_path.suffix.lower() in {".yml", ".yaml"}:
            if yaml is None:
                return {}
            try:
                parsed = yaml.safe_load(content)
            except Exception:
                return {}
            return parsed if isinstance(parsed, dict) else {}

        if config_path.name == ".env":
            return _parse_env(content)

        return super().parse_config(config_path)

    def get_available_models(self) -> list[ModelInfo]:
        # Aider supports many models; keep a representative set.
        return [
            ModelInfo(
                id="openai:gpt-4o",
                display_name="GPT-4o (via Aider)",
                provider="openai",
                capabilities=["code", "chat", "vision"],
            ),
            ModelInfo(
                id="anthropic:claude-3-5-sonnet",
                display_name="Claude 3.5 Sonnet (via Aider)",
                provider="anthropic",
                capabilities=["code", "chat"],
            ),
            ModelInfo(
                id="google:gemini-2.5-pro",
                display_name="Gemini 2.5 Pro (via Aider)",
                provider="google",
                capabilities=["code", "chat", "vision"],
            ),
            ModelInfo(
                id="ollama:qwen2.5-coder:32b",
                display_name="Qwen2.5 Coder 32B (via Ollama + Aider)",
                provider="ollama",
                capabilities=["code", "chat"],
            ),
        ]

    def build_command(self, model: str, prompt_file: Path, cwd: Path) -> list[str]:
        _ = cwd
        prompt = prompt_file.read_text(encoding="utf-8", errors="replace")
        cmd = ["aider", "--message", prompt, "--yes"]
        model_name = model.split(":", 1)[1] if ":" in model else model
        if model_name:
            cmd.extend(["--model", model_name])
        return cmd


PLUGIN = AiderCLI()

