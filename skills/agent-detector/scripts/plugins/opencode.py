from __future__ import annotations

from pathlib import Path

from .base import ModelInfo, SimpleCLIPlugin


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


PLUGIN = OpenCodeCLI()
