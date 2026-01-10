#!/usr/bin/env python3
"""
Demo shell for VHS recordings - outputs realistic Claude Code-style responses.
"""
import sys

# ANSI color codes for terminal output
BOLD = "\033[1m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
CYAN = "\033[36m"
DIM = "\033[2m"
RESET = "\033[0m"

SCENARIOS = {
    "create-and-run-prompt": [
        f"""
{BOLD}I'll create an optimized prompt for adding a login form with email validation.{RESET}

{GREEN}✓{RESET} Saved prompt to {CYAN}./prompts/001-login-form-validation.md{RESET}

{BOLD}What's next?{RESET}

  1. Run prompt now
  2. Review/edit prompt first
  3. Save for later
  4. Other

Choose (1-4): {DIM}1{RESET}
""",
        f"""
{BOLD}📊 AI Quota Status:{RESET}
  Claude: 18% (5h) {GREEN}✅{RESET} | Codex: 0% (5h) {GREEN}✅{RESET} | Z.AI: 1% {GREEN}✅{RESET}

{BOLD}Execute via:{RESET}

  {BOLD}Claude:{RESET}
  1. Claude - sub-agent in current context
  2. Claude (worktree) - isolated git worktree

  {BOLD}Codex (OpenAI):{RESET}
  3. codex - GPT-5.1-code standard
  4. codex-high - higher token limit

  {BOLD}Other:{RESET}
  5. gemini - Gemini 3 Flash
  6. zai - Z.AI GLM-4.7

  {DIM}Recommended: codex (your preferred agent){RESET}

Choose (1-6): {DIM}3{RESET}
""",
        f"""
{BOLD}Execution Summary{RESET}

  Prompt   Model   Log
  ──────   ─────   ───
  001      codex   ~/.claude/cli-logs/codex-001-20260110-143052.log

{BOLD}Status{RESET}

  Prompt                          Status              Monitor
  ──────                          ──────              ───────
  001 - Login Form Validation     {GREEN}🟢 Running{RESET} (PID 48291)   Background agent

{BOLD}Quick commands:{RESET}
  {DIM}# Tail log{RESET}
  tail -f ~/.claude/cli-logs/codex-001-20260110-143052.log

{GREEN}✅{RESET} {BOLD}Prompt 001 is now running with codex{RESET}
""",
    ],
    "multi-model-delegation": [
        f"""
{GREEN}✓{RESET} Saved prompt to {CYAN}./prompts/001-billing-summary.md{RESET}
""",
        f"""
{GREEN}✓{RESET} Saved prompt to {CYAN}./prompts/002-audit-log-filter.md{RESET}
""",
        f"""
{GREEN}✓{RESET} Saved prompt to {CYAN}./prompts/003-csv-export.md{RESET}

{BOLD}3 prompts created.{RESET} Ready for parallel execution.
""",
        f"""
{BOLD}📊 AI Quota Status:{RESET}
  Claude: 45% (5h) {YELLOW}⚠️{RESET} | Codex: 12% (5h) {GREEN}✅{RESET} | Gemini: 7% {GREEN}✅{RESET}

{BOLD}Execution Summary{RESET}

  Prompt   Model    Worktree                                    Log
  ──────   ─────    ────────                                    ───
  001      gemini   .worktrees/myapp-prompt-001-20260110/       ~/.claude/cli-logs/gemini-001-*.log
  002      gemini   .worktrees/myapp-prompt-002-20260110/       ~/.claude/cli-logs/gemini-002-*.log
  003      gemini   .worktrees/myapp-prompt-003-20260110/       ~/.claude/cli-logs/gemini-003-*.log

{BOLD}Status{RESET}

  Prompt                    Status              Monitor
  ──────                    ──────              ───────
  001 - Billing Summary     {GREEN}🟢 Running{RESET} (PID 51023)   Background agent
  002 - Audit Log Filter    {GREEN}🟢 Running{RESET} (PID 51024)   Background agent
  003 - CSV Export          {GREEN}🟢 Running{RESET} (PID 51025)   Background agent

{GREEN}✅{RESET} {BOLD}3 prompts running in parallel with gemini{RESET}
""",
    ],
    "worktree-isolation": [
        f"""
{BOLD}Execution Summary{RESET}

  Prompt   Model   Worktree                                         Branch
  ──────   ─────   ────────                                         ──────
  005      codex   .worktrees/myapp-prompt-005-20260110-143521/     prompt/005-refactor-auth

{BOLD}Worktree created:{RESET}
  Path:   {CYAN}.worktrees/myapp-prompt-005-20260110-143521/{RESET}
  Branch: {CYAN}prompt/005-refactor-auth{RESET}

{DIM}Your main branch remains clean. Changes isolated in worktree.{RESET}

{BOLD}Status{RESET}

  Prompt                    Status              Monitor
  ──────                    ──────              ───────
  005 - Refactor Auth       {GREEN}🟢 Running{RESET} (PID 52891)   Background agent

{BOLD}Quick commands:{RESET}
  {DIM}# Check worktree{RESET}
  cd .worktrees/myapp-prompt-005-20260110-143521/

  {DIM}# Merge when done{RESET}
  git checkout main && git merge prompt/005-refactor-auth

{GREEN}✅{RESET} {BOLD}Prompt 005 running in isolated worktree{RESET}
""",
    ],
    "verification-loop": [
        f"""
{BOLD}🔄 Verification Loop Started{RESET}
  Prompt: 010
  Model: codex
  Max iterations: 5
  Completion marker: VERIFICATION_COMPLETE

{BOLD}Iteration 1/5{RESET}
  Status: {YELLOW}NEEDS_RETRY{RESET}
  Reason: 3 tests failing

{BOLD}Iteration 2/5{RESET}
  Status: {YELLOW}NEEDS_RETRY{RESET}
  Reason: 2 lint errors remain

{BOLD}Iteration 3/5{RESET}
  Status: {GREEN}VERIFICATION_COMPLETE{RESET}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

{GREEN}✅{RESET} {BOLD}Loop completed successfully after 3 iterations{RESET}

  All tests passing
  Lint clean
  Build succeeded
""",
    ],
    "quota-awareness": [
        f"""
{BOLD}🔍 AI CLI Usage Checker{RESET}
   2026-01-10 14:35:22

══════════════════════════════════════════════════
  {BOLD}Claude Code{RESET}
══════════════════════════════════════════════════
  {GREEN}✅{RESET} Connected

  5-Hour Window:
    Used:      18.0%
    Remaining: 82.0%
    Resets in: 3h 24m

  7-Day Window:
    Used:      11.0%
    Remaining: 89.0%
    Resets in: 142h 24m

══════════════════════════════════════════════════
  {BOLD}OpenAI Codex{RESET}
══════════════════════════════════════════════════
  {GREEN}✅{RESET} Connected
  Plan: pro

  5h Window:
    Used:      0%
    Remaining: 100%
    Resets in: 5h 0m

══════════════════════════════════════════════════
  {BOLD}Google Gemini{RESET}
══════════════════════════════════════════════════
  {GREEN}✅{RESET} Connected

  gemini-3-flash:     7% used
  gemini-2.5-pro:    10% used
  gemini-3-pro:      10% used

══════════════════════════════════════════════════
  {BOLD}Z.AI{RESET}
══════════════════════════════════════════════════
  {GREEN}✅{RESET} Connected

  Token Quota:
    Used:      1%
    Remaining: 99%
    Resets in: 58m

{BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━{RESET}
{BOLD}Summary:{RESET} Claude: 18% | Codex: 0% | Gemini: 7% | Z.AI: 1%
{DIM}Recommendation: codex has the most capacity{RESET}
""",
    ],
    "llms-txt-creation": [
        f"""
{BOLD}Creating llms.txt documentation prompt{RESET}

  Target:    pydantic-ai
  Category:  python/
  Output:    python/pydantic-ai.llms-full.txt

{GREEN}✓{RESET} Saved prompt to {CYAN}/storage/projects/docker/llms_txt/prompts/014-pydantic-ai-docs.md{RESET}

{DIM}Prompt created in llms_txt repository (cross-repo){RESET}

{BOLD}Next step:{RESET}
  /run-prompt 014 --model codex --prompt-file /storage/projects/docker/llms_txt/prompts/014-pydantic-ai-docs.md
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

    for step in steps:
        try:
            input()  # Wait for Enter (from VHS tape)
        except EOFError:
            return 0
        print(step.strip())
        print()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
