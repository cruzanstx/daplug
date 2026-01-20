from __future__ import annotations

from pathlib import Path

from .base import ModelInfo, SimpleCLIPlugin


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


PLUGIN = GeminiCLI()
