<objective>
Add Claude Code CLI support to daplug's prompt executor so prompts can be executed via the local `claude` CLI (Claude Code) in one-shot (non-interactive) mode.

This is needed so daplug can be orchestrated from OpenCode (or other CLIs) while still using the user's Claude Max plan for execution.
</objective>

<context>
Repository: daplug (Claude Code plugin) with a Python prompt executor.

Current behavior:
- `skills/prompt-executor/scripts/executor.py` supports running prompts via Codex CLI, Gemini CLI, and OpenCode.
- The `claude` model is currently treated as "handled by Task subagent" (no external CLI command), which does not work when daplug is being driven from OpenCode.

Relevant files to examine:
- @skills/prompt-executor/scripts/executor.py
- @skills/cli-detector/scripts/router.py
- @skills/cli-detector/scripts/providers.py
- @skills/cli-detector/scripts/detect_clis.py
- @skills/cli-detector/tests/
- @skills/prompt-executor/tests/
- @skills/prompt-executor/scripts/test_executor_markers.py
- @commands/run-prompt.md
- @CLAUDE.md
</context>

<requirements>
1. Add a new executor CLI wrapper option for Claude Code:
   - Support `--cli claude` as an override.
   - Also accept aliases `--cli claudecode` and `--cli cc` (normalize them internally to `claude`).
   - Keep existing overrides (`codex`, `opencode`) working exactly as-is.

2. Add two model shorthands intended for Claude Code execution:
   - A Sonnet shorthand (target: "cc sonnet 4.5")
   - An Opus shorthand (target: "cc opus 4.6")

   Implementation details:
   - Use the actual model IDs that the `claude` CLI supports (determine via `claude --help`, `claude config`, or other authoritative local discovery).
   - If the `claude` CLI cannot select models programmatically, implement the shorthands in a way that is still useful:
     - Either route both to the same default model and clearly document the limitation, OR
     - Introduce a safe, explicit configuration mechanism (no secrets in git) and document it.

3. One-shot / non-interactive mode:
   - Ensure the executor can run `claude` in a fully headless, non-interactive mode.
   - Do not require a human to answer prompts.
   - Prefer robust prompt input handling that does not break on large prompts (avoid unsafe shell quoting; avoid argv length issues when possible).

4. Integrate with the /detect-clis routing table:
   - The executor already tries to resolve command templates via the cli-detector router.
   - Update the routing + executor glue so that `cli_name == "claude"` produces a real runnable command and the correct input mode.

5. Keep backwards compatibility:
   - No behavior changes for existing non-Claude models.
   - The `claude` shorthand should continue to work when running inside Claude Code contexts.
   - If `claude` CLI is not installed or not detected, return a clear error and suggest running `/daplug:detect-clis`.

6. Tests:
   - Add/extend unit tests to cover:
     - `--cli` override normalization (claude/claudecode/cc)
     - Command generation for claude-backed models
     - Router resolution path vs fallback path behavior
     - That large prompt content is passed safely (at least at the command-construction level)
</requirements>

<implementation>
Thoroughly analyze existing patterns and consider multiple approaches before coding.

Follow these steps:
1. Read @CLAUDE.md and follow repo conventions (naming, model tables, command patterns).
2. Inspect `executor.py`:
   - Find where `--cli` is defined and extend choices and normalization.
   - Find `_cli_info_from_router()` and update it so `cli == "claude"` returns a runnable command and correct `stdin_mode`.
   - Ensure `run_cli()` and `run_cli_foreground()` can support the chosen input strategy for claude.
3. Inspect cli-detector router/provider code to understand how `claude` is represented and what command template is expected.
4. Implement the claude CLI command template:
   - Determine the correct non-interactive invocation of `claude`.
   - If it requires a PTY, set `needs_pty` accordingly, but only if truly required.
   - Prefer stdin/file-based prompt passing if the CLI supports it; otherwise ensure argument passing is safe and reliable.
5. Add the two model shorthands for Sonnet/Opus:
   - Add them consistently in model lists (executor argparse choices, router cache/provider mapping, docs if needed).
   - Ensure help text and display strings are accurate.
6. Update docs where it matters (only what's necessary):
   - `commands/run-prompt.md` and/or relevant docs so users know how to use `--cli claude` and the new shorthands.

Constraints:
- Do not add new runtime dependencies.
- Do not add interactive prompts.
- Do not log secrets/tokens.
- Keep changes minimal and focused on enabling Claude Code CLI execution.
</implementation>

<verification>
Run these checks and include the command outputs in your reasoning before declaring done:

```bash
# Prompt executor tests
python3 -m pytest skills/prompt-executor/tests -v
python3 -m pytest skills/prompt-executor/scripts/test_executor_markers.py -v

# CLI detector tests (if modified)
python3 -m pytest skills/cli-detector/tests -v

# Basic sanity: help output includes new options
python3 skills/prompt-executor/scripts/executor.py --help
```

If any tests fail for reasons unrelated to your changes, call that out explicitly and do not "fix" unrelated areas.
</verification>

<success_criteria>
- `python3 skills/prompt-executor/scripts/executor.py 005 --model claude --cli claude --info-only` returns CLI info that includes a runnable `command` and a non-None `stdin_mode`.
- `--cli claudecode` and `--cli cc` behave identically to `--cli claude`.
- Two Claude Code model shorthands exist and are wired end-to-end (choices, routing, display), using real model IDs if possible.
- All relevant unit tests pass.
</success_criteria>