#!/usr/bin/env python3
"""Tests for the post-push-detect.sh hook script."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "post-push-detect.sh"


def run_hook(input_json: str | dict) -> subprocess.CompletedProcess:
    """Run the hook script with the given JSON on stdin."""
    if isinstance(input_json, dict):
        input_json = json.dumps(input_json)
    return subprocess.run(
        ["bash", str(SCRIPT)],
        input=input_json,
        capture_output=True,
        text=True,
        timeout=10,
    )


def make_bash_event(command: str, exit_code: int = 0) -> dict:
    """Build a minimal PostToolUse event payload."""
    return {
        "tool_input": {"command": command},
        "tool_response": {"exit_code": exit_code},
    }


# --- Detection: should trigger ---


class TestGitPushDetection:
    def test_simple_push(self):
        result = run_hook(make_bash_event("git push"))
        assert result.returncode == 0
        output = json.loads(result.stdout)
        assert "hookSpecificOutput" in output
        assert "pipeline-deploy-monitor" in output["hookSpecificOutput"]["additionalContext"]

    def test_push_with_remote(self):
        result = run_hook(make_bash_event("git push origin"))
        assert result.returncode == 0
        output = json.loads(result.stdout)
        ctx = output["hookSpecificOutput"]["additionalContext"]
        assert "origin" in ctx

    def test_push_with_remote_and_branch(self):
        result = run_hook(make_bash_event("git push origin main"))
        assert result.returncode == 0
        output = json.loads(result.stdout)
        ctx = output["hookSpecificOutput"]["additionalContext"]
        assert "origin" in ctx
        assert "main" in ctx

    def test_push_with_flags(self):
        result = run_hook(make_bash_event("git push --set-upstream origin feature/x"))
        assert result.returncode == 0
        output = json.loads(result.stdout)
        ctx = output["hookSpecificOutput"]["additionalContext"]
        assert "origin" in ctx
        assert "feature/x" in ctx

    def test_push_force(self):
        result = run_hook(make_bash_event("git push --force origin main"))
        assert result.returncode == 0
        assert json.loads(result.stdout)["hookSpecificOutput"]

    def test_push_u_flag(self):
        result = run_hook(make_bash_event("git push -u origin dev"))
        assert result.returncode == 0
        output = json.loads(result.stdout)
        ctx = output["hookSpecificOutput"]["additionalContext"]
        assert "origin" in ctx
        assert "dev" in ctx


# --- Non-detection: should NOT trigger ---


class TestNonPushCommands:
    def test_git_commit(self):
        result = run_hook(make_bash_event("git commit -m 'test'"))
        assert result.returncode == 0
        assert result.stdout.strip() == ""

    def test_git_pull(self):
        result = run_hook(make_bash_event("git pull"))
        assert result.returncode == 0
        assert result.stdout.strip() == ""

    def test_git_status(self):
        result = run_hook(make_bash_event("git status"))
        assert result.returncode == 0
        assert result.stdout.strip() == ""

    def test_non_git_command(self):
        result = run_hook(make_bash_event("ls -la"))
        assert result.returncode == 0
        assert result.stdout.strip() == ""

    def test_grep_git_push(self):
        """A grep for 'git push' should not trigger."""
        result = run_hook(make_bash_event("grep 'git push' README.md"))
        assert result.returncode == 0
        assert result.stdout.strip() == ""

    def test_echo_git_push(self):
        result = run_hook(make_bash_event("echo git push"))
        assert result.returncode == 0
        assert result.stdout.strip() == ""


# --- Failed push: should NOT trigger ---


class TestFailedPush:
    def test_push_nonzero_exit(self):
        result = run_hook(make_bash_event("git push origin main", exit_code=1))
        assert result.returncode == 0
        assert result.stdout.strip() == ""

    def test_push_exit_128(self):
        result = run_hook(make_bash_event("git push", exit_code=128))
        assert result.returncode == 0
        assert result.stdout.strip() == ""


# --- Edge cases ---


class TestEdgeCases:
    def test_empty_input(self):
        result = run_hook("")
        assert result.returncode == 0
        assert result.stdout.strip() == ""

    def test_whitespace_only_input(self):
        result = run_hook("   \n  ")
        assert result.returncode == 0
        assert result.stdout.strip() == ""

    def test_invalid_json(self):
        result = run_hook("not json at all")
        assert result.returncode == 0
        assert result.stdout.strip() == ""

    def test_missing_command_field(self):
        result = run_hook({"tool_input": {}, "tool_response": {"exit_code": 0}})
        assert result.returncode == 0
        assert result.stdout.strip() == ""

    def test_missing_exit_code(self):
        """Missing exit_code should still trigger (assume success)."""
        result = run_hook({"tool_input": {"command": "git push"}, "tool_response": {}})
        assert result.returncode == 0
        output = json.loads(result.stdout)
        assert "hookSpecificOutput" in output

    def test_push_options_skipped(self):
        """--push-option takes an argument; the next token should not be treated as remote."""
        result = run_hook(make_bash_event("git push --push-option ci.skip origin main"))
        assert result.returncode == 0
        output = json.loads(result.stdout)
        ctx = output["hookSpecificOutput"]["additionalContext"]
        assert "origin" in ctx
        assert "main" in ctx

    def test_double_dash_separator(self):
        result = run_hook(make_bash_event("git push -- origin main"))
        assert result.returncode == 0
        output = json.loads(result.stdout)
        ctx = output["hookSpecificOutput"]["additionalContext"]
        assert "origin" in ctx
