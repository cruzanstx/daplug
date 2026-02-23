<objective>
Design and implement a secure Claude CLI sandbox mode for daplug prompt-executor that defaults to isolated execution, enforces explicit tool allowlisting, and denies risky operations by default while preserving backward compatibility for existing `--cli claude` behavior.

This matters because prompt execution can run arbitrary tool actions; the goal is to reduce blast radius for routine usage without breaking established workflows.
</objective>

<context>
Project: daplug Claude Code plugin with prompt execution orchestration.

Read `./CLAUDE.md` first for repository conventions, architecture, model routing, and release process.

Primary implementation area is expected in:
- `./skills/prompt-executor/scripts/executor.py`
- `./skills/prompt-executor/SKILL.md`
- `./commands/run-prompt.md`
- tests related to prompt-executor/config parsing

Preserve existing behavior for users who currently run `--cli claude` without sandbox-specific flags.
</context>

<requirements>
1. Add a secure sandbox mode for Claude CLI execution with a safe default profile.
2. Default sandbox execution to isolated git worktree mode (or equivalent isolation in current architecture).
3. Introduce explicit allowlist handling for tools/actions and deny risky operations by default.
4. Keep backward compatibility:
   - Existing `--cli claude` invocation paths must continue to work.
   - Existing flags and defaults must not regress unless explicitly tied to sandbox-mode behavior.
5. Provide clear configuration and runtime override semantics (e.g., safe defaults + opt-out/opt-in switches).
6. Include robust validation and error messaging for invalid allowlist/denylist combinations.
</requirements>

<implementation>
Thoroughly analyze current prompt-executor flow and consider multiple approaches before coding.

Implement in this order:
1. Model current Claude execution path, worktree handling, and permission/tool invocation flow.
2. Add sandbox-mode configuration surface (CLI flags and/or config-reader integration) with conservative defaults.
3. Define risky operations policy and enforce deny-by-default in sandbox mode.
4. Add explicit allowlist support for permitted tools/actions.
5. Preserve backward compatibility by gating behavior changes behind sandbox-aware defaults that do not break legacy `--cli claude` usage.
6. Update docs/help text where user-facing behavior changes.

Constraints (with rationale):
- Do not weaken safety checks to pass tests; security controls must be deterministic and testable.
- Avoid broad wildcard allowlists by default, because least-privilege defaults are the core objective.
- Keep changes focused to prompt-executor and closely related command/config surfaces to minimize regression scope.

For maximum efficiency, whenever you need to perform multiple independent operations, invoke all relevant tools simultaneously rather than sequentially.
After receiving tool results, carefully reflect on their quality and determine optimal next steps before proceeding.
</implementation>

<output>
Modify/create only what is necessary, using relative paths such as:
- `./skills/prompt-executor/scripts/executor.py` - sandbox policy, defaults, and enforcement
- `./skills/prompt-executor/SKILL.md` - updated CLI options and behavior docs
- `./commands/run-prompt.md` - command usage updates for sandbox mode
- `./skills/prompt-executor/tests/...` - unit and integration smoke tests
- `./CHANGELOG.md` or project-standard release notes location - release notes entry
</output>

<verification>
**Unit Tests** (REQUIRED for regression protection):
```bash
# Run prompt-executor related tests
cd skills/prompt-executor && python3 -m pytest -v
```

Create/update tests for:
- [ ] Sandbox mode defaulting to isolated worktree behavior
- [ ] Allowlist enforcement for permitted tools/actions
- [ ] Deny-by-default blocking of risky operations
- [ ] Backward compatibility for existing `--cli claude` behavior
- [ ] Invalid config/flag combinations and error handling

Integration smoke tests:
- [ ] Execute representative prompt-executor invocation with sandbox defaults
- [ ] Execute legacy `--cli claude` invocation path and verify no regression
- [ ] Validate config-driven overrides and CLI flag precedence

Before declaring complete, verify your work:
- [ ] All updated/new unit tests pass
- [ ] Integration smoke checks pass
- [ ] Help/docs output reflects new sandbox options accurately
- [ ] Release notes mention security model, defaults, and compatibility guarantees
</verification>

<success_criteria>
- Secure sandbox mode exists and is enforced for Claude execution path with deny-by-default controls.
- Explicit allowlist is required for elevated/sensitive actions in sandbox mode.
- Default behavior improves isolation (worktree-first) without breaking existing `--cli claude` workflows.
- Unit tests and integration smoke tests cover critical paths and pass.
- Release notes clearly communicate the change, migration/compatibility expectations, and operator guidance.
</success_criteria>