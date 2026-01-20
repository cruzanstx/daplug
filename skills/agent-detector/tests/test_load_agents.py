"""Tests for load_agents.py CLI."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

# Ensure scripts directory is in path
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from load_agents import (
    main,
    _render_markdown_table,
    _model_summary,
    _cli_label,
    _collect_issues,
    _json_payload,
)


class TestRenderMarkdownTable:
    def test_basic_table(self):
        result = _render_markdown_table(["A", "B"], [["1", "2"], ["3", "4"]])
        assert "| A | B |" in result
        assert "| 1 | 2 |" in result
        assert "| 3 | 4 |" in result
        assert "| - | - |" in result  # separator row

    def test_handles_empty_cells(self):
        result = _render_markdown_table(["Col"], [[""], [None]])
        assert "| Col |" in result
        # Should not crash with None/empty

    def test_handles_newlines_in_cells(self):
        result = _render_markdown_table(["Col"], [["line1\nline2"]])
        assert "\n" not in result.split("\n")[2]  # Cell content should have newline stripped


class TestModelSummary:
    def test_empty_list(self):
        assert _model_summary([]) == "-"

    def test_single_model(self):
        assert _model_summary([{"id": "gpt-4"}]) == "gpt-4"

    def test_strips_prefix(self):
        result = _model_summary([{"id": "openai:gpt-4"}])
        assert result == "gpt-4"

    def test_truncates_at_max(self):
        models = [{"id": f"model-{i}"} for i in range(10)]
        result = _model_summary(models, max_items=3)
        assert result.endswith(", …")
        assert result.count(",") == 3  # 2 separators + 1 ellipsis separator


class TestCliLabel:
    def test_claude_becomes_claude_code(self):
        assert _cli_label("claude") == "claude-code"

    def test_other_unchanged(self):
        assert _cli_label("codex") == "codex"
        assert _cli_label("gemini") == "gemini"


class TestCollectIssues:
    def test_empty_cache(self):
        assert _collect_issues({}) == []

    def test_extracts_issues_from_installed_clis(self):
        cache = {
            "clis": {
                "test-cli": {
                    "installed": True,
                    "issues": [{"type": "config_missing", "message": "No config"}],
                }
            }
        }
        issues = _collect_issues(cache)
        assert len(issues) == 1
        assert issues[0]["cli"] == "test-cli"
        assert issues[0]["type"] == "config_missing"

    def test_ignores_uninstalled_clis(self):
        cache = {
            "clis": {
                "not-installed": {
                    "installed": False,
                    "issues": [{"type": "test"}],
                }
            }
        }
        assert _collect_issues(cache) == []


class TestJsonPayload:
    def test_adds_schema_version(self):
        payload = _json_payload({})
        assert payload["schema_version"] == "1.0"

    def test_includes_issues(self):
        cache = {
            "clis": {
                "cli1": {"installed": True, "issues": [{"type": "test"}]}
            }
        }
        payload = _json_payload(cache)
        assert "issues" in payload
        assert len(payload["issues"]) == 1


class TestMainCli:
    @patch("load_agents.scan_all_clis")
    def test_json_flag_outputs_json(self, mock_scan, capsys):
        mock_cache = MagicMock()
        mock_cache.to_dict.return_value = {"clis": {}, "providers": {}}
        mock_scan.return_value = mock_cache

        result = main(["--json"])

        assert result == 0
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert "schema_version" in data

    @patch("load_agents.scan_all_clis")
    def test_human_output_includes_headers(self, mock_scan, capsys):
        mock_cache = MagicMock()
        mock_cache.to_dict.return_value = {
            "clis": {
                "codex": {"installed": True, "version": "1.0", "models": [], "issues": []}
            },
            "providers": {},
        }
        mock_scan.return_value = mock_cache

        result = main([])

        assert result == 0
        captured = capsys.readouterr()
        assert "Found" in captured.out
        assert "CLI" in captured.out

    @patch("load_agents._clear_cache_files")
    @patch("load_agents.scan_all_clis")
    def test_reset_clears_cache(self, mock_scan, mock_clear, capsys):
        mock_clear.return_value = [Path("/tmp/test.json")]
        mock_cache = MagicMock()
        mock_cache.to_dict.return_value = {"clis": {}, "providers": {}}
        mock_scan.return_value = mock_cache

        result = main(["--reset"])

        assert result == 0
        mock_clear.assert_called_once()
        captured = capsys.readouterr()
        assert "Cleared" in captured.out or "Rescanning" in captured.out
