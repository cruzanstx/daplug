from __future__ import annotations

from pathlib import Path

from .base import ModelInfo, SimpleCLIPlugin

try:
    import yaml  # type: ignore
except ModuleNotFoundError:  # pragma: no cover
    yaml = None


class GooseCLI(SimpleCLIPlugin):
    _name = "goose"
    _display_name = "Goose"
    _executable_names = ["goose"]
    _version_cmd = ["goose", "--version"]
    _supported_providers = ["openai", "anthropic", "google", "openrouter", "ollama"]
    _config_paths = [
        Path("~/.config/goose/config.yaml"),
    ]

    def parse_config(self, config_path: Path) -> dict:
        if yaml is None:
            return {}
        try:
            content = config_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return {}
        try:
            parsed = yaml.safe_load(content)
        except Exception:
            return {}
        return parsed if isinstance(parsed, dict) else {}

    def get_available_models(self) -> list[ModelInfo]:
        # Goose supports many models depending on the configured provider.
        return [
            ModelInfo(
                id="openai:gpt-4o",
                display_name="GPT-4o (via Goose)",
                provider="openai",
                capabilities=["code", "chat", "vision"],
            ),
            ModelInfo(
                id="anthropic:claude",
                display_name="Claude (via Goose)",
                provider="anthropic",
                capabilities=["code", "chat"],
            ),
            ModelInfo(
                id="google:gemini",
                display_name="Gemini (via Goose)",
                provider="google",
                capabilities=["code", "chat", "vision"],
            ),
            ModelInfo(
                id="ollama:ollama",
                display_name="Ollama (via Goose)",
                provider="ollama",
                capabilities=["code", "chat"],
            ),
        ]

    def build_command(self, model: str, prompt_file: Path, cwd: Path) -> list[str]:
        _ = model, prompt_file, cwd
        # Goose is primarily interactive.
        return ["goose", "session"]


PLUGIN = GooseCLI()

