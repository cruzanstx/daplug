from __future__ import annotations

import json
import os
import platform
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def cache_age_seconds(cache: "AgentCache") -> Optional[float]:
    try:
        scanned = datetime.fromisoformat(cache.last_scanned)
    except (TypeError, ValueError):
        return None
    if scanned.tzinfo is None:
        scanned = scanned.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - scanned).total_seconds()


def is_cache_fresh(cache: "AgentCache", max_age_seconds: float) -> bool:
    age = cache_age_seconds(cache)
    if age is None:
        return False
    return age <= max_age_seconds


def default_cache_path() -> Path:
    override = os.environ.get("DAPLUG_AGENT_CACHE_PATH")
    if override:
        return Path(os.path.expandvars(os.path.expanduser(override)))
    return Path.home() / ".claude" / "daplug-clis.json"


@dataclass
class RouteEntry:
    preferred: str
    fallbacks: list[str] = field(default_factory=list)
    provider: Optional[str] = None


@dataclass
class UserPreferences:
    default_cli: str = "codex"
    model_overrides: dict[str, RouteEntry] = field(default_factory=dict)


@dataclass
class AgentCache:
    schema_version: str = "1.0"
    last_scanned: str = field(default_factory=now_iso)
    scan_duration_ms: int = 0
    host: dict[str, Any] = field(
        default_factory=lambda: {"os": platform.system(), "arch": platform.machine()}
    )
    clis: dict[str, Any] = field(default_factory=dict)
    providers: dict[str, Any] = field(default_factory=dict)
    routing: dict[str, RouteEntry] = field(default_factory=dict)
    user_preferences: UserPreferences = field(default_factory=UserPreferences)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["routing"] = {k: asdict(v) for k, v in self.routing.items()}
        data["user_preferences"] = asdict(self.user_preferences)
        data["user_preferences"]["model_overrides"] = {
            k: asdict(v) for k, v in self.user_preferences.model_overrides.items()
        }
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AgentCache":
        routing = {
            k: RouteEntry(**v) for k, v in (data.get("routing") or {}).items() if isinstance(v, dict)
        }
        prefs_raw = data.get("user_preferences") or {}
        model_overrides_raw = prefs_raw.get("model_overrides") or {}
        prefs = UserPreferences(
            default_cli=prefs_raw.get("default_cli", "codex"),
            model_overrides={
                k: RouteEntry(**v)
                for k, v in model_overrides_raw.items()
                if isinstance(v, dict)
            },
        )
        return cls(
            schema_version=data.get("schema_version", "1.0"),
            last_scanned=data.get("last_scanned", now_iso()),
            scan_duration_ms=int(data.get("scan_duration_ms", 0) or 0),
            host=data.get("host") or {},
            clis=data.get("clis") or {},
            providers=data.get("providers") or {},
            routing=routing,
            user_preferences=prefs,
        )


def load_cache_file(path: Optional[Path] = None) -> Optional[AgentCache]:
    candidate_paths = [path] if path is not None else [default_cache_path(), Path("/tmp/daplug-clis.json")]
    for candidate in candidate_paths:
        if candidate is None:
            continue
        try:
            content = candidate.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        try:
            raw = json.loads(content)
        except json.JSONDecodeError:
            return None
        if not isinstance(raw, dict):
            return None
        return AgentCache.from_dict(raw)
    return None


def save_cache_file(cache: AgentCache, path: Optional[Path] = None) -> None:
    candidate_paths = [path] if path is not None else [default_cache_path(), Path("/tmp/daplug-clis.json")]
    last_error: Optional[OSError] = None
    for candidate in candidate_paths:
        if candidate is None:
            continue
        try:
            candidate.parent.mkdir(parents=True, exist_ok=True)
            candidate.write_text(
                json.dumps(cache.to_dict(), indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            return
        except OSError as exc:
            last_error = exc
            continue
    if last_error is not None:
        raise last_error
