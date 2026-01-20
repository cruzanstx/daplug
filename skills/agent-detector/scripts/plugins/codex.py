from __future__ import annotations

from pathlib import Path

from .base import ModelInfo, SimpleCLIPlugin


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
