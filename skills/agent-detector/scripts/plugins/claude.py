from __future__ import annotations

from pathlib import Path

from .base import ModelInfo, SimpleCLIPlugin


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


PLUGIN = ClaudeCLI()
