import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.append(str(SCRIPT_DIR))

from cache import AgentCache, load_cache_file, save_cache_file  # noqa: E402


def test_cache_round_trip(tmp_path):
    path = tmp_path / "cache.json"
    cache = AgentCache()
    cache.clis["codex"] = {"installed": True, "version": "1.0"}
    save_cache_file(cache, path=path)
    loaded = load_cache_file(path=path)
    assert loaded is not None
    assert loaded.schema_version == "1.0"
    assert loaded.clis["codex"]["installed"] is True


def test_load_cache_missing_returns_none(tmp_path):
    missing = tmp_path / "missing.json"
    assert load_cache_file(path=missing) is None
