from __future__ import annotations

import importlib
import pkgutil
from typing import Optional

from .base import ProviderPlugin

_PROVIDER_CACHE: Optional[list[ProviderPlugin]] = None


def discover_providers() -> list[ProviderPlugin]:
    global _PROVIDER_CACHE
    if _PROVIDER_CACHE is not None:
        return list(_PROVIDER_CACHE)

    discovered: list[ProviderPlugin] = []
    for module_info in pkgutil.iter_modules(__path__):
        name = module_info.name
        if name.startswith("_") or name in {"base"}:
            continue
        module = importlib.import_module(f"{__name__}.{name}")
        plugin = getattr(module, "PLUGIN", None)
        if isinstance(plugin, ProviderPlugin):
            discovered.append(plugin)

    discovered.sort(key=lambda p: p.name)
    _PROVIDER_CACHE = discovered
    return list(discovered)


def get_provider(name: str) -> Optional[ProviderPlugin]:
    name = name.strip().lower()
    for provider in discover_providers():
        if provider.name.lower() == name:
            return provider
    return None
