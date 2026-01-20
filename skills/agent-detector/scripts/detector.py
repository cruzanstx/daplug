#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Optional

from cache import (
    AgentCache,
    RouteEntry,
    UserPreferences,
    is_cache_fresh,
    load_cache_file,
    save_cache_file,
)
from plugins import discover_plugins, get_plugin
from plugins.base import configissue_to_dict, modelinfo_to_dict
from providers import discover_providers
from providers.base import ProviderStatus


def load_cache() -> Optional[AgentCache]:
    """Load cached detection results."""
    return load_cache_file()


def save_cache(cache: AgentCache) -> None:
    """Save detection results to cache file."""
    save_cache_file(cache)


def _model_family(model_id: str) -> str:
    if ":" in model_id:
        provider, rest = model_id.split(":", 1)
        if provider == "anthropic":
            return "claude"
        if provider == "openai":
            return "gpt"
        if provider == "google":
            return "gemini"
        if provider == "zai":
            return "glm"
        if provider in {"local", "ollama", "lmstudio"}:
            return "local"
        _ = rest
        return provider
    return "unknown"


def _default_routing_for_model(model_id: str) -> RouteEntry:
    family = _model_family(model_id)
    if family == "claude":
        return RouteEntry(preferred="claude", fallbacks=["aider", "goose", "opencode", "codex"])
    if family == "gpt":
        return RouteEntry(preferred="codex", fallbacks=["aider", "goose", "opencode"])
    if family == "gemini":
        return RouteEntry(preferred="gemini", fallbacks=["aider", "goose", "opencode"])
    if family == "glm":
        return RouteEntry(preferred="opencode", fallbacks=["codex"])
    if family == "local":
        return RouteEntry(preferred="aider", fallbacks=["codex", "opencode", "goose"])
    if family == "openrouter":
        return RouteEntry(preferred="aider", fallbacks=["goose", "codex", "opencode"])
    if family == "github":
        return RouteEntry(preferred="ghcopilot", fallbacks=[])
    return RouteEntry(preferred="codex", fallbacks=["aider", "goose", "opencode", "gemini", "claude"])


def scan_all_clis(force_refresh: bool = False) -> AgentCache:
    """Scan all registered CLI plugins and return results."""
    if not force_refresh:
        cached = load_cache()
        if cached is not None and is_cache_fresh(cached, max_age_seconds=24 * 60 * 60):
            discovered = {p.name for p in discover_plugins()}
            cached_names = set((cached.clis or {}).keys())
            if discovered.issubset(cached_names):
                return cached

    start = time.time()
    cache = AgentCache(user_preferences=UserPreferences(default_cli="codex"))

    # Scan CLIs
    for plugin in discover_plugins():
        installed, exe = plugin.detect_installation()
        version = plugin.get_version() if installed else None
        config_paths = [str(p) for p in plugin.get_config_paths()]

        config: dict = {}
        for p in plugin.get_config_paths():
            if p.exists():
                config = plugin.parse_config(p)
                break

        models = [modelinfo_to_dict(m) for m in plugin.get_available_models()]
        for m in models:
            m.setdefault("family", _model_family(str(m.get("id", ""))))
            m.setdefault("display", m.get("display_name"))

        issues = [configissue_to_dict(i) for i in plugin.detect_issues()]

        cache.clis[plugin.name] = {
            "installed": bool(installed),
            "version": version,
            "executable": exe,
            "config_paths": config_paths,
            "config": config,
            "models": models,
            "supported_providers": plugin.get_supported_providers(),
            "issues": issues,
        }

    # Scan providers (best-effort, fast timeouts)
    for provider in discover_providers():
        running, endpoint = provider.detect_running()
        loaded_models: list[str] = []
        if running:
            loaded_models = provider.list_models(endpoint)
        status = ProviderStatus(
            running=running,
            endpoint=endpoint,
            loaded_models=loaded_models,
            compatible_clis=provider.compatible_clis(),
        )
        cache.providers[provider.name] = {
            "running": status.running,
            "endpoint": status.endpoint,
            "loaded_models": status.loaded_models,
            "compatible_clis": status.compatible_clis,
        }

    # Compute naive routing from discovered models
    for cli in cache.clis.values():
        for model in cli.get("models", []):
            model_id = model.get("id")
            if not model_id:
                continue
            cache.routing.setdefault(model_id, _default_routing_for_model(str(model_id)))

    cache.scan_duration_ms = int((time.time() - start) * 1000)
    save_cache(cache)
    return cache


def get_preferred_cli(model: str) -> Optional[str]:
    """Get the best CLI to run a given model."""
    cache = load_cache()
    if cache is None:
        cache = scan_all_clis(force_refresh=True)

    override = cache.user_preferences.model_overrides.get(model)
    route = override or cache.routing.get(model) or _default_routing_for_model(model)

    candidates = [route.preferred, *route.fallbacks]
    for name in candidates:
        cli = cache.clis.get(name)
        if cli and cli.get("installed"):
            return name
    return None


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="daplug agent detector (Phase 1)")
    p.add_argument("--scan", action="store_true", help="Scan all plugins and output JSON")
    p.add_argument("--verbose", action="store_true", help="Verbose progress output (stderr)")
    p.add_argument("--check", metavar="NAME", help="Check a specific CLI plugin")
    p.add_argument("--list-plugins", action="store_true", help="List all CLI plugins")
    p.add_argument("--refresh", action="store_true", help="Force refresh (ignore cache)")
    return p


def main(argv: Optional[list[str]] = None) -> int:
    args = _build_parser().parse_args(argv)

    if args.list_plugins:
        for plugin in discover_plugins():
            print(f"{plugin.name}\t{plugin.display_name}")
        return 0

    if args.check:
        plugin = get_plugin(args.check)
        if plugin is None:
            print(f"Unknown CLI plugin: {args.check}", file=sys.stderr)
            return 2
        installed, exe = plugin.detect_installation()
        payload = {
            "name": plugin.name,
            "display_name": plugin.display_name,
            "installed": installed,
            "executable": exe,
            "version": plugin.get_version() if installed else None,
            "config_paths": [str(p) for p in plugin.get_config_paths()],
            "supported_providers": plugin.get_supported_providers(),
            "issues": [configissue_to_dict(i) for i in plugin.detect_issues()],
        }
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0

    if args.scan:
        if args.verbose:
            print("Scanning CLIs/providers...", file=sys.stderr)
        cache = scan_all_clis(force_refresh=bool(args.refresh))
        print(json.dumps(cache.to_dict(), indent=2, sort_keys=True))
        return 0

    _build_parser().print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
