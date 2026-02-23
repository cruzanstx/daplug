<objective>
Fix daplug prompt-executor so explicit `--cli opencode` with OpenAI shorthand models (for example `--model codex`) routes to OpenCode correctly instead of failing with a router-selected codex mismatch error.

This matters because users need deterministic CLI override behavior and currently a documented override path is broken in real execution.
</objective>

<context>
Read `./CLAUDE.md` first for project conventions and release workflow.

Target areas to examine:
- `./skills/prompt-executor/scripts/executor.py`
- `./skills/cli-detector/scripts/router.py`
- `./skills/cli-detector/scripts/detect_clis.py` (if routing metadata assumptions matter)
- `./skills/prompt-executor/tests/`
- `./commands/run-prompt.md` and `./skills/prompt-executor/SKILL.md` for behavior/docs consistency

Observed failing scenario:
- `--model codex --cli opencode --variant high --worktree --loop --run`
- Error: router selected codex mismatch, despite explicit cli override and OpenCode availability.
</context>

<requirements>
1. Make explicit `--cli opencode` overrides work for supported models (including `codex`, `codex-high`, `codex-xhigh`, `gpt52*`, `zai`, `glm5`, and local opencode-capable shorthands).
2. Preserve strict override semantics:
   - If override is unsupported, return a clear actionable error.
   - If override is supported, do not fail due to router default selection.
3. Keep backward compatibility for existing default routing when `--cli` is not provided.
4. Ensure `--variant` still maps correctly for OpenCode runs.
5. Keep output metadata truthful (`selected_cli`, `cli_command`, `cli_display`).
</requirements>

<implementation>
Thoroughly analyze the current resolver flow and consider multiple approaches before editing.

Implement in this sequence:
1. Identify where router selection is compared against explicit override and why supported overrides are rejected.
2. Adjust resolution logic so explicit supported override controls final command builder even when router prefers another CLI by default.
3. Preserve and improve guardrails for truly unsupported combinations.
4. Add/adjust tests for:
   - explicit supported override works (`codex` + `--cli opencode`)
   - unsupported override still fails clearly
   - no-override default behavior unchanged
   - variant propagation with OpenCode
5. Update docs only if user-facing behavior text needs correction.

For maximum efficiency, whenever you need to perform multiple independent operations, invoke all relevant tools simultaneously rather than sequentially.
After receiving tool results, carefully reflect on their quality and determine optimal next steps before proceeding.
</implementation>

<output>
Modify/create files with relative paths such as:
- `./skills/prompt-executor/scripts/executor.py`
- `./skills/prompt-executor/tests/test_executor_variants.py`
- `./skills/prompt-executor/tests/test_executor_logging.py` (only if needed)
- `./commands/run-prompt.md` (if docs need adjustment)
- `./skills/prompt-executor/SKILL.md` (if docs need adjustment)
</output>

<verification>
**Unit Tests** (REQUIRED for regression protection):
```bash
python3 -m pytest skills/prompt-executor/tests -v
```

Create/update tests for:
- [ ] `--model codex --cli opencode` resolves to OpenCode command path
- [ ] OpenCode run includes `--variant` when provided
- [ ] Unsupported override combinations still fail with actionable message
- [ ] Existing default routing with no explicit override remains unchanged

Before declaring complete, verify your work:
- [ ] All prompt-executor tests pass
- [ ] Reproduction command no longer fails with router mismatch for supported override
- [ ] Output metadata reflects actual selected CLI and command
</verification>

<success_criteria>
- Supported explicit `--cli opencode` overrides work in real execution paths.
- Unsupported combinations continue to fail safely and clearly.
- Backward compatibility is preserved for default routing.
- Tests prove the fix and prevent regression.
</success_criteria>