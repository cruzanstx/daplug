import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.append(str(SCRIPT_DIR))

from providers import discover_providers, get_provider  # noqa: E402


def test_discover_providers_lists_defaults():
    names = [p.name for p in discover_providers()]
    assert "lmstudio" in names
    assert "ollama" in names


def test_get_provider_unknown_none():
    assert get_provider("nope") is None
