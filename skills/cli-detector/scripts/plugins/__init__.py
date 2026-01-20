from __future__ import annotations

import importlib
import pkgutil
from typing import Optional

from .base import CLIPlugin

_PLUGIN_CACHE: Optional[list[CLIPlugin]] = None


def discover_plugins() -> list[CLIPlugin]:
    """Auto-discover all CLI plugins in this directory."""
    global _PLUGIN_CACHE
    if _PLUGIN_CACHE is not None:
        return list(_PLUGIN_CACHE)

    discovered: list[CLIPlugin] = []
    for module_info in pkgutil.iter_modules(__path__):
        name = module_info.name
        if name.startswith("_") or name in {"base"}:
            continue
        module = importlib.import_module(f"{__name__}.{name}")
        plugin = getattr(module, "PLUGIN", None)
        if isinstance(plugin, CLIPlugin):
            discovered.append(plugin)
            continue
        getter = getattr(module, "get_plugin", None)
        if callable(getter):
            candidate = getter()
            if isinstance(candidate, CLIPlugin):
                discovered.append(candidate)

    discovered.sort(key=lambda p: p.name)
    _PLUGIN_CACHE = discovered
    return list(discovered)


def get_plugin(name: str) -> Optional[CLIPlugin]:
    """Get a specific plugin by name."""
    name = name.strip().lower()
    for plugin in discover_plugins():
        if plugin.name.lower() == name:
            return plugin
    return None
