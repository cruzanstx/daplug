<objective>
Implement unified variant/reasoning support in daplug prompt-executor so reasoning effort works consistently across Codex and OpenCode, including explicit `--cli opencode` behavior.

This matters because users expect reasoning controls to map predictably regardless of CLI wrapper, and current behavior can silently diverge.
</objective>

<context>
Read `./CLAUDE.md` first and follow existing conventions.

This task targets executor command resolution and runtime invocation behavior in:
- `./skills/prompt-executor/scripts/executor.py`
- `./skills/prompt-executor/SKILL.md`
- `./commands/run-prompt.md`
- any relevant tests under `./skills/prompt-executor/tests/`

Current known behavior:
- Codex aliases like `codex-high` and `codex-xhigh` encode `model_reasoning_effort` in command templates.
- OpenCode supports variant-based reasoning via `opencode run --variant ...`.
- Daplug executor currently does not pass `--variant` to OpenCode runs.
</context>

<requirements>
1. Add explicit variant support to prompt-executor CLI surface:
   - Introduce `--variant` option with clear help text and supported values.
2. Normalize model resolution so reasoning settings are represented centrally (not scattered in hardcoded aliases).
3. Ensure per-CLI mapping is explicit:
   - Codex path maps variant/reasoning to Codex-compatible settings.
   - OpenCode path passes `--variant` for supported cases.
4. Fix CLI override semantics:
   - When `--cli opencode` is requested for supported models, use OpenCode path or fail with actionable error.
   - Never silently ignore explicit `--cli` intent.
5. Preserve backward compatibility:
   - Existing aliases (`codex-high`, `codex-xhigh`, `gpt52-high`, etc.) continue to work.
   - Existing non-variant workflows remain functional.
6. Keep output metadata truthful:
   - `cli_command`, `cli_display`, and run info should reflect actual executed command.
</requirements>

<implementation>
Thoroughly analyze existing command-building flow and consider multiple approaches before coding.

Implement step-by-step:
1. Introduce a normalized internal execution config (for example: base model, selected CLI, variant, stdin mode, env, command).
2. Add `--variant` argparse support and precedence rules:
   - explicit `--variant` should override alias-derived defaults.
3. Refactor command synthesis into per-CLI builders:
   - Codex builder
   - OpenCode builder
   - Claude/Claude Code builder
4. Wire OpenCode builder to append `--variant` when provided and valid.
5. Add validation for unsupported variant/model/cli combinations with clear user-facing errors.
6. Update docs/help text in related command/skill docs.

Constraints (and why they matter):
- Do not use silent fallback for explicit CLI overrides, because hidden routing changes make debugging impossible.
- Do not remove legacy aliases yet; preserve compatibility while migrating internals.
- Keep refactor scoped to executor and adjacent docs/tests to reduce regression risk.

For maximum efficiency, whenever you need to perform multiple independent operations, invoke all relevant tools simultaneously rather than sequentially.
After receiving tool results, carefully reflect on their quality and determine optimal next steps before proceeding.
</implementation>

<output>
Modify files using relative paths, for example:
- `./skills/prompt-executor/scripts/executor.py` - variant parsing, normalization, command builders
- `./skills/prompt-executor/SKILL.md` - updated usage/options docs
- `./commands/run-prompt.md` - user-facing run flag docs
- `./skills/prompt-executor/tests/...` - unit/integration coverage for variant behavior
</output>

<verification>
**Unit Tests** (REQUIRED for regression protection):
```bash
cd skills/prompt-executor && python3 -m pytest -v
```

Create/update tests for:
- [ ] `--variant` parsing and precedence vs alias defaults
- [ ] Codex command mapping for high/xhigh variants
- [ ] OpenCode command includes `--variant` when requested
- [ ] Explicit `--cli opencode` is respected or errors clearly
- [ ] Legacy aliases remain backward-compatible
- [ ] Invalid variant combinations return actionable errors

Integration smoke tests:
- [ ] Info-only output for representative model/cli/variant combinations
- [ ] One run-path smoke check for codex variant command rendering
- [ ] One run-path smoke check for opencode variant command rendering

Before declaring complete, verify:
- [ ] All related tests pass
- [ ] No regressions in existing model routing behavior
- [ ] Help text and docs match actual implementation
</verification>

<success_criteria>
- Executor has a first-class `--variant` mechanism with deterministic behavior.
- OpenCode runs can receive reasoning variants via `--variant`.
- Codex/OpenCode mapping is explicit, test-covered, and backward-compatible.
- Explicit CLI override intent is honored (or fails clearly), never silently ignored.
</success_criteria>