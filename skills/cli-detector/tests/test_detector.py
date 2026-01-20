import json
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.append(str(SCRIPT_DIR))

import detector  # noqa: E402


def test_preferred_cli_falls_back_when_not_installed(monkeypatch):
    fake = detector.AgentCache()
    fake.clis = {"codex": {"installed": False}, "opencode": {"installed": True}}
    fake.routing = {"openai:gpt-5.2": detector.RouteEntry(preferred="codex", fallbacks=["opencode"])}
    monkeypatch.setattr(detector, "load_cache", lambda: fake)
    assert detector.get_preferred_cli("openai:gpt-5.2") == "opencode"


def test_detector_cli_list_plugins(capsys):
    rc = detector.main(["--list-plugins"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "codex" in out


def test_detector_cli_scan_outputs_json(monkeypatch, capsys):
    # Avoid slow scans by stubbing scan function.
    cache = detector.AgentCache()
    cache.clis = {"codex": {"installed": True}}

    monkeypatch.setattr(detector, "scan_all_clis", lambda force_refresh=False: cache)

    rc = detector.main(["--scan"])
    assert rc == 0
    out = capsys.readouterr().out
    parsed = json.loads(out)
    assert parsed["clis"]["codex"]["installed"] is True
