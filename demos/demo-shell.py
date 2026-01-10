#!/usr/bin/env python3
import sys
from textwrap import dedent

SCENARIOS = {
    "create-and-run-prompt": [
        """
        Creating prompt: 001-login-form.md
        Type: feature
        Template: XML structured

        Saved: /storage/projects/docker/daplug/prompts/001-login-form.md

        Preview (excerpt):
        <objective>
          Build a login form with email validation.
        </objective>
        <context>
          Stack: React + Tailwind
        </context>
        <requirements>
          - Email must match a standard pattern
          - Password min length 8
          - Inline error messages
        </requirements>
        <verification>
          - npm test
          - npm run lint
        </verification>

        Executor options:
          1) codex  gpt-5.2-codex  [recommended]
          2) gemini 3-flash
          3) zai    glm-4.7
        Selected: codex
        """,
        """
        Run prompt 001 with model: codex
        Model selection:
          [*] codex   gpt-5.2-codex
          [ ] gemini  3-flash
          [ ] zai     glm-4.7

        Workdir: /storage/projects/docker/daplug
        Log: ~/.claude/cli-logs/prompt-001-codex-20260109-103015.log
        Monitor: spawned (readonly-log-watcher)
        Status: running
        """,
    ],
    "multi-model-delegation": [
        """
        Creating prompt: 001-billing-summary.md
        Type: feature
        Saved: /storage/projects/docker/daplug/prompts/001-billing-summary.md
        """,
        """
        Creating prompt: 002-audit-log-filter.md
        Type: feature
        Saved: /storage/projects/docker/daplug/prompts/002-audit-log-filter.md
        """,
        """
        Creating prompt: 003-csv-export.md
        Type: feature
        Saved: /storage/projects/docker/daplug/prompts/003-csv-export.md
        """,
        """
        Quota check (cclimits):
          Claude: 18% | Codex: 0% | Gemini 3-Flash: 7% | Z.AI: 1%
        Recommendation: Use gemini (3-Flash)

        Parallel execution enabled:
          Prompts: 001 002 003
          Model: gemini (3-Flash)
          Workdir: /storage/projects/docker/daplug

        Launching:
          001 -> ~/.claude/cli-logs/prompt-001-gemini-20260109-103112.log
          002 -> ~/.claude/cli-logs/prompt-002-gemini-20260109-103112.log
          003 -> ~/.claude/cli-logs/prompt-003-gemini-20260109-103112.log
        Monitors: spawned (3)
        Status: running
        """,
    ],
    "worktree-isolation": [
        """
        Worktree mode enabled
        Base branch: main
        Worktree created:
          Path: /storage/projects/docker/worktrees/daplug-prompt-005-20260109-103201
          Branch: feature/prompt-005-20260109-103201

        Dependencies:
          Detected: package-lock.json (npm)
          Installed: npm ci

        Main branch (current repo):
          Status: clean
          No files modified

        Worktree execution:
          Prompt: 005
          Model: codex (default)
          Log: ~/.claude/cli-logs/prompt-005-codex-20260109-103201.log
        """,
    ],
    "verification-loop": [
        """
        Loop mode enabled (max iterations: 5)
        Completion marker: VERIFICATION_COMPLETE

        Iteration 1:
          Result: NEEDS_RETRY: tests failing (3)
        Iteration 2:
          Result: NEEDS_RETRY: lint errors (2)
        Iteration 3:
          Result: VERIFICATION_COMPLETE

        Loop finished after 3 iterations
        Status: success
        """,
    ],
    "quota-awareness": [
        """
        AI CLI Usage (5h window)
          Claude: 18% used
          Codex: 0% used
          Gemini: 7% used (3-Flash)
          Z.AI: 1% used

        Recommendation:
          codex has the most capacity
        """,
    ],
    "llms-txt-creation": [
        """
        llms_txt repo: /storage/projects/docker/llms_txt
        Category: python/
        Target: python/pydantic-ai.llms-full.txt

        Prompt created:
          /storage/projects/docker/llms_txt/prompts/014-pydantic-ai.md

        Next:
          /run-prompt 014 --model codex
          (uses --prompt-file for cross-repo execution)
        """,
    ],
}


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: demo-shell.py <scenario>")
        print("Available: " + ", ".join(sorted(SCENARIOS.keys())))
        return 2

    scenario = sys.argv[1]
    steps = SCENARIOS.get(scenario)
    if not steps:
        print(f"Unknown scenario: {scenario}")
        print("Available: " + ", ".join(sorted(SCENARIOS.keys())))
        return 2

    title = scenario.replace("-", " ")
    print(f"daplug demo: {title}")
    print("")

    for step in steps:
        try:
            input("daplug> ")
        except EOFError:
            return 0
        print(dedent(step).strip("\n"))
        print("")

    try:
        input("daplug> ")
    except EOFError:
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
