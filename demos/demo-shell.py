#!/usr/bin/env python3
"""
Demo shell for VHS recordings - simulates Claude Code interface.
"""
import sys
import time

# ANSI color codes matching Claude Code's terminal output
BOLD = "\033[1m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
CYAN = "\033[36m"
MAGENTA = "\033[35m"
DIM = "\033[2m"
RESET = "\033[0m"
BLUE = "\033[34m"

# Claude Code style elements
BULLET = f"{MAGENTA}●{RESET}"
PROMPT = f"{BOLD}>{RESET} "


def print_slow(text: str, delay: float = 0.01) -> None:
    """Print text with a slight delay to simulate typing/thinking."""
    for char in text:
        print(char, end="", flush=True)
        time.sleep(delay)
    print()


def claude_response(text: str) -> str:
    """Format text as a Claude response."""
    lines = text.strip().split("\n")
    formatted = []
    for i, line in enumerate(lines):
        if i == 0:
            formatted.append(f"  {line}")
        else:
            formatted.append(f"  {line}")
    return "\n".join(formatted)


SCENARIOS = {
    "create-and-run-prompt": [
        # User types command, Claude responds
        ("user", '/create-prompt "add a login form with email validation"'),
        ("thinking", "Analyzing request..."),
        ("response", f"""
{BULLET} I'll create an optimized prompt for adding a login form with email validation.

{GREEN}✓{RESET} Saved prompt to {CYAN}./prompts/001-login-form-validation.md{RESET}

{BOLD}What's next?{RESET}

  1. Run prompt now
  2. Review/edit prompt first
  3. Save for later
  4. Other

  Choose (1-4):"""),
        ("user", "1"),
        ("response", f"""
{BULLET} {BOLD}📊 AI Quota Status:{RESET}
  Claude: 18% (5h) {GREEN}✅{RESET} | Codex: 0% (5h) {GREEN}✅{RESET} | Z.AI: 1% {GREEN}✅{RESET}

{BULLET} {BOLD}Execute via:{RESET}

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

  Choose (1-6):"""),
        ("user", "3"),
        ("tool", "Bash", "python3 executor.py 001 --model codex --run"),
        ("response", f"""
{BULLET} {BOLD}Execution Summary{RESET}

  Prompt   Model   Log
  ──────   ─────   ───
  001      codex   ~/.claude/cli-logs/codex-001-20260110.log

{BULLET} {BOLD}Status{RESET}

  Prompt                          Status                 Monitor
  ──────                          ──────                 ───────
  001 - Login Form Validation     {GREEN}🟢 Running{RESET} (PID 48291)    Background agent

{GREEN}✅{RESET} {BOLD}Prompt 001 is now running with codex{RESET}

  {DIM}# Tail log{RESET}
  tail -f ~/.claude/cli-logs/codex-001-20260110.log"""),
    ],

    "multi-model-delegation": [
        ("user", '/create-prompt "add a billing summary table"'),
        ("response", f"{GREEN}✓{RESET} Saved prompt to {CYAN}./prompts/001-billing-summary.md{RESET}"),
        ("user", '/create-prompt "add audit log filters"'),
        ("response", f"{GREEN}✓{RESET} Saved prompt to {CYAN}./prompts/002-audit-log-filter.md{RESET}"),
        ("user", '/create-prompt "add CSV export"'),
        ("response", f"""{GREEN}✓{RESET} Saved prompt to {CYAN}./prompts/003-csv-export.md{RESET}

{BULLET} {BOLD}3 prompts created.{RESET} Ready for parallel execution."""),
        ("user", "/run-prompt 001 002 003 --parallel --model gemini"),
        ("tool", "Bash", "python3 executor.py 001 002 003 --model gemini --parallel --run"),
        ("response", f"""
{BULLET} {BOLD}📊 AI Quota Status:{RESET}
  Claude: 45% (5h) {YELLOW}⚠️{RESET} | Codex: 12% (5h) {GREEN}✅{RESET} | Gemini: 7% {GREEN}✅{RESET}

{BULLET} {BOLD}Execution Summary{RESET}

  Prompt   Model    Worktree                               Log
  ──────   ─────    ────────                               ───
  001      gemini   .worktrees/myapp-prompt-001/           ~/.claude/cli-logs/gemini-001.log
  002      gemini   .worktrees/myapp-prompt-002/           ~/.claude/cli-logs/gemini-002.log
  003      gemini   .worktrees/myapp-prompt-003/           ~/.claude/cli-logs/gemini-003.log

{BULLET} {BOLD}Status{RESET}

  Prompt                    Status                 Monitor
  ──────                    ──────                 ───────
  001 - Billing Summary     {GREEN}🟢 Running{RESET} (PID 51023)    Background agent
  002 - Audit Log Filter    {GREEN}🟢 Running{RESET} (PID 51024)    Background agent
  003 - CSV Export          {GREEN}🟢 Running{RESET} (PID 51025)    Background agent

{GREEN}✅{RESET} {BOLD}3 prompts running in parallel with gemini{RESET}"""),
    ],

    "worktree-isolation": [
        ("user", "/run-prompt 005 --worktree"),
        ("tool", "Bash", "python3 executor.py 005 --worktree --run"),
        ("response", f"""
{BULLET} {BOLD}Execution Summary{RESET}

  Prompt   Model   Worktree                                       Branch
  ──────   ─────   ────────                                       ──────
  005      codex   .worktrees/myapp-prompt-005-20260110/          prompt/005-refactor-auth

{BULLET} {BOLD}Worktree created:{RESET}
  Path:   {CYAN}.worktrees/myapp-prompt-005-20260110/{RESET}
  Branch: {CYAN}prompt/005-refactor-auth{RESET}

  {DIM}Your main branch remains clean. Changes isolated in worktree.{RESET}

{BULLET} {BOLD}Status{RESET}

  Prompt                    Status                 Monitor
  ──────                    ──────                 ───────
  005 - Refactor Auth       {GREEN}🟢 Running{RESET} (PID 52891)    Background agent

{GREEN}✅{RESET} {BOLD}Prompt 005 running in isolated worktree{RESET}

  {DIM}# Merge when done{RESET}
  git checkout main && git merge prompt/005-refactor-auth"""),
    ],

    "verification-loop": [
        ("user", "/run-prompt 010 --loop --max-iterations 5"),
        ("tool", "Bash", "python3 executor.py 010 --loop --max-iterations 5 --run"),
        ("response", f"""
{BULLET} {BOLD}🔄 Verification Loop Started{RESET}
  Prompt: 010
  Model: codex
  Max iterations: 5
  Completion marker: VERIFICATION_COMPLETE

{BULLET} {BOLD}Iteration 1/5{RESET}
  Status: {YELLOW}NEEDS_RETRY{RESET}
  Reason: 3 tests failing

{BULLET} {BOLD}Iteration 2/5{RESET}
  Status: {YELLOW}NEEDS_RETRY{RESET}
  Reason: 2 lint errors remain

{BULLET} {BOLD}Iteration 3/5{RESET}
  Status: {GREEN}VERIFICATION_COMPLETE{RESET}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

{GREEN}✅{RESET} {BOLD}Loop completed successfully after 3 iterations{RESET}

  All tests passing
  Lint clean
  Build succeeded"""),
    ],

    "quota-awareness": [
        ("user", "/cclimits"),
        ("tool", "Bash", "npx cclimits"),
        ("response", f"""
{BULLET} {BOLD}🔍 AI CLI Usage Checker{RESET}
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
  {GREEN}✅{RESET} Connected  |  Plan: pro

  5h Window:
    Used:      0%
    Remaining: 100%

══════════════════════════════════════════════════
  {BOLD}Google Gemini{RESET}
══════════════════════════════════════════════════
  {GREEN}✅{RESET} Connected

  gemini-3-flash:     7% used
  gemini-2.5-pro:    10% used

══════════════════════════════════════════════════
  {BOLD}Z.AI{RESET}
══════════════════════════════════════════════════
  {GREEN}✅{RESET} Connected

  Token Quota: 1% used

{BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━{RESET}
{BOLD}Summary:{RESET} Claude: 18% | Codex: 0% | Gemini: 7% | Z.AI: 1%"""),
    ],

    "llms-txt-creation": [
        ("user", "/create-llms-txt pydantic-ai"),
        ("thinking", "Checking llms_txt repository..."),
        ("response", f"""
{BULLET} {BOLD}Creating llms.txt documentation prompt{RESET}

  Target:    pydantic-ai
  Category:  python/
  Output:    python/pydantic-ai.llms-full.txt

{GREEN}✓{RESET} Saved prompt to {CYAN}/storage/projects/docker/llms_txt/prompts/014-pydantic-ai-docs.md{RESET}

  {DIM}Prompt created in llms_txt repository (cross-repo){RESET}

{BULLET} {BOLD}Next step:{RESET}
  /run-prompt 014 --model codex"""),
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
        return 2

    for step in steps:
        step_type = step[0]

        if step_type == "user":
            # Wait for VHS to type the command
            try:
                user_input = input(PROMPT)
            except EOFError:
                return 0
            # The typed command is already shown by VHS

        elif step_type == "thinking":
            print(f"  {DIM}{step[1]}{RESET}")
            time.sleep(0.3)

        elif step_type == "tool":
            tool_name, tool_cmd = step[1], step[2]
            print(f"  {DIM}Using {tool_name}...{RESET}")
            time.sleep(0.2)

        elif step_type == "response":
            print(step[1].strip())
            print()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
