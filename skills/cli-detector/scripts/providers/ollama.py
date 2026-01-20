from __future__ import annotations

from .base import ProviderPlugin, get_provider_endpoint, http_get_json, join_url, strip_v1


class OllamaProvider(ProviderPlugin):
    @property
    def name(self) -> str:
        return "ollama"

    @property
    def display_name(self) -> str:
        return "Ollama"

    @property
    def default_endpoint(self) -> str:
        return "http://localhost:11434/v1"

    def detect_running(self, timeout_s: float = 0.3) -> tuple[bool, str]:
        endpoint = get_provider_endpoint("ollama") or self.default_endpoint
        root = strip_v1(endpoint)
        data = http_get_json(join_url(root, "api/version"), timeout_s=timeout_s)
        return (data is not None), endpoint

    def list_models(self, endpoint: str, timeout_s: float = 0.5) -> list[str]:
        # Prefer OpenAI-compatible endpoint if available, then fall back to native /api/tags.
        data = http_get_json(join_url(endpoint, "models"), timeout_s=timeout_s)
        if isinstance(data, dict) and isinstance(data.get("data"), list):
            ids: list[str] = []
            for item in data.get("data") or []:
                if not isinstance(item, dict):
                    continue
                model_id = item.get("id")
                if model_id:
                    ids.append(str(model_id))
            if ids:
                return ids

        root = strip_v1(endpoint)
        data = http_get_json(join_url(root, "api/tags"), timeout_s=timeout_s) or {}
        models = data.get("models", [])
        ids = []
        for item in models:
            if not isinstance(item, dict):
                continue
            name = item.get("name")
            if name:
                ids.append(str(name))
        return ids

    def compatible_clis(self) -> list[str]:
        return ["aider", "goose", "opencode"]


PLUGIN = OllamaProvider()
