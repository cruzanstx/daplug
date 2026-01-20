from __future__ import annotations

from .base import ProviderPlugin, http_get_json


class LMStudioProvider(ProviderPlugin):
    @property
    def name(self) -> str:
        return "lmstudio"

    @property
    def display_name(self) -> str:
        return "LM Studio"

    @property
    def default_endpoint(self) -> str:
        return "http://localhost:1234"

    def detect_running(self, timeout_s: float = 0.3) -> tuple[bool, str]:
        endpoint = self.default_endpoint
        data = http_get_json(f"{endpoint}/v1/models", timeout_s=timeout_s)
        return (data is not None), endpoint

    def list_models(self, endpoint: str, timeout_s: float = 0.5) -> list[str]:
        data = http_get_json(f"{endpoint}/v1/models", timeout_s=timeout_s) or {}
        models = data.get("data", [])
        ids: list[str] = []
        for item in models:
            model_id = item.get("id")
            if model_id:
                ids.append(str(model_id))
        return ids

    def compatible_clis(self) -> list[str]:
        return ["codex", "opencode"]


PLUGIN = LMStudioProvider()
