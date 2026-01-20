from __future__ import annotations

from .base import ProviderPlugin, get_provider_endpoint, http_get_json, join_url


class VLLMProvider(ProviderPlugin):
    @property
    def name(self) -> str:
        return "vllm"

    @property
    def display_name(self) -> str:
        return "vLLM"

    @property
    def default_endpoint(self) -> str:
        return "http://localhost:8000/v1"

    def detect_running(self, timeout_s: float = 0.3) -> tuple[bool, str]:
        endpoint = get_provider_endpoint("vllm") or self.default_endpoint
        data = http_get_json(join_url(endpoint, "models"), timeout_s=timeout_s)
        return (data is not None), endpoint

    def list_models(self, endpoint: str, timeout_s: float = 0.5) -> list[str]:
        data = http_get_json(join_url(endpoint, "models"), timeout_s=timeout_s) or {}
        models = data.get("data", [])
        ids: list[str] = []
        for item in models:
            if not isinstance(item, dict):
                continue
            model_id = item.get("id")
            if model_id:
                ids.append(str(model_id))
        return ids

    def compatible_clis(self) -> list[str]:
        return ["aider", "codex", "opencode"]


PLUGIN = VLLMProvider()

