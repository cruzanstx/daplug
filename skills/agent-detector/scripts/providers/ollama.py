from __future__ import annotations

from .base import ProviderPlugin, http_get_json


class OllamaProvider(ProviderPlugin):
    @property
    def name(self) -> str:
        return "ollama"

    @property
    def display_name(self) -> str:
        return "Ollama"

    @property
    def default_endpoint(self) -> str:
        return "http://localhost:11434"

    def detect_running(self, timeout_s: float = 0.3) -> tuple[bool, str]:
        endpoint = self.default_endpoint
        data = http_get_json(f"{endpoint}/api/version", timeout_s=timeout_s)
        return (data is not None), endpoint

    def list_models(self, endpoint: str, timeout_s: float = 0.5) -> list[str]:
        data = http_get_json(f"{endpoint}/api/tags", timeout_s=timeout_s) or {}
        models = data.get("models", [])
        ids: list[str] = []
        for item in models:
            name = item.get("name")
            if name:
                ids.append(str(name))
        return ids

    def compatible_clis(self) -> list[str]:
        return ["aider", "goose", "opencode"]


PLUGIN = OllamaProvider()
