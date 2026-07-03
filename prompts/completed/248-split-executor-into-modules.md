<objective>
Split the 3,508-line `skills/prompt-executor/scripts/executor.py` into focused, independently-testable modules WITHOUT changing any runtime behavior and WITHOUT breaking the existing test suite. This file has been the home of nearly every recent bug (#14, #17, #20, #21) because sandboxing, loop control, the model registry, worktree management, and CLI launching are all tangled in one namespace. Extract cohesive modules so each concern can be reasoned about and tested in isolation.

This is a PURE STRUCTURAL REFACTOR. Zero functional change. If a single test assertion about actual behavior changes, you have done it wrong.
</objective>

<context>
This is the daplug Claude Code plugin repo. Read CLAUDE.md for conventions.

@skills/prompt-executor/scripts/executor.py — the monolith to split (3,508 lines)
@skills/prompt-executor/tests/ — five test files that import `executor` and heavily monkeypatch its internals

The file has clear functional clusters (line numbers approximate):
- Paths/config (23-183): get_repo_root, _read_config_value, get_cli_logs_dir, get_worktree_dir, detect_default_branch
- Repo-state snapshot & diff/stall detection (183-419): repo_state_snapshot, repo_state_delta, _has_real_file_changes, _detect_stalled, _detect_impossible_gate, _get_git_head
- Worktree management (421-695, plus 1833-1912): create_worktree, install_worktree_dependencies, normalize_worktree_path, ensure_worktree_permissions
- Prompt resolution (696-842): expand_prompt_input, resolve_prompt(s)
- Model registry & CLI command building (843-1436): _load_model_registry, MODEL_SPECS, all _build_*_command, get_cli_info
- Sandbox (1437-1831): resolve_sandbox_config, build_bwrap_args, sandbox_preflight, maybe_wrap_command_with_sandbox
- Loop state & verification (1914-3129): loop state I/O, check_completion_marker, wrap_prompt_with_verification_protocol, run_cli, run_cli_foreground, run_verification_loop(_background)
- main() (3130-end): argparse entry point
</context>

<critical_constraint>
**The test suite monkeypatches `executor.<name>` extensively. This is the #1 risk and the whole difficulty of this task.**

Tests do `import executor` and then reference/patch these attributes (verified counts):
- Module attributes patched for indirection: `executor.subprocess` (15), `executor.shutil` (7), `executor.Path` (7)
- Functions patched via monkeypatch.setattr: get_cli_info, run_cli, run_cli_foreground, run_verification_loop, run_verification_loop_background, resolve_sandbox_config, build_bwrap_args, sandbox_preflight, check_bwrap_available, repo_state_snapshot, create_worktree, detect_default_branch, get_repo_root, get_cli_logs_dir, get_loop_state_dir, _read_config_value, _require_claude_cli, _resolve_router_command, wrap_prompt_with_verification_protocol
- Constants/data read: MODEL_SPECS, MODEL_CHOICES, MODEL_REGISTRY_BY_NAME, LEGACY_MODEL_DISPLAY, INSTRUCTIONS_END_SENTINEL, SANDBOX_ENV_PASSTHROUGH, _SANDBOX_PREFLIGHT_CACHE, _REQUIRED_MODEL_FIELDS, _ALLOWED_STDIN_MODES, _sandbox_passthrough_env

Two hazards that will silently break tests if ignored:
1. **Attribute resolution.** After moving code out, `import executor; executor.foo` must STILL resolve for every name currently referenced by tests. Re-export moved names into executor's namespace (e.g. `from .sandbox import build_bwrap_args, sandbox_preflight, ...`).
2. **Monkeypatch indirection.** When a test does `monkeypatch.setattr(executor, "subprocess", fake)` or `monkeypatch.setattr(executor, "sandbox_preflight", fake)`, the patch only affects code that looks the name up THROUGH the `executor` module object at call time. If `run_cli` moves to loop.py and calls `sandbox_preflight` via loop.py's own import, patching `executor.sandbox_preflight` will NOT intercept it, and the test will exercise real code. You must resolve this. Acceptable strategies (pick per case, document choice in report):
   a. Keep the caller and callee in the SAME module so intra-module calls stay patchable there, and update the test to patch that module.
   b. Update the affected tests to patch the new module location (these tests assert on internal structure, so changing the patch target is allowed — but the ASSERTIONS must not change).
   Whichever you choose, the full suite must pass and behavior must be identical.
</critical_constraint>

<requirements>
1. Extract cohesive modules under `skills/prompt-executor/scripts/` (suggested, adjust with justification): `paths.py`, `repostate.py`, `worktree.py`, `models.py`, `sandbox.py`, `loop.py`. Keep `executor.py` as the CLI entry point (`main()` + argparse) that imports and re-exports the public surface so `import executor` remains a complete facade.
2. Preserve the `executor.<name>` attribute surface for EVERY name in the critical_constraint list — re-export moved functions, constants, and the `subprocess`/`shutil`/`Path` module references that tests patch.
3. No circular imports. If two clusters are mutually dependent, either keep them together or introduce a small shared module (e.g. paths/constants) that both import. Document the dependency graph in the report.
4. No behavior change, no new dependencies, no new features. Do not "improve" logic while moving it — move verbatim, adjust only imports.
5. Match existing style. Each new module gets a one-line module docstring stating its responsibility.
6. Update tests ONLY where a monkeypatch target must move to a new module location (per hazard 2). Do NOT weaken or delete any assertion. If you move a test's patch target, the test must still verify the same behavior.
7. `manage-models.py` reads/derives from executor at runtime — verify it still works (it imports the registry). The generated docs must stay in sync.
</requirements>

<verification>
All must pass before declaring completion:

```bash
# Full suite — same set CI runs — must be GREEN with the SAME test count (362) or more (if you split a test file)
for suite in skills/prompt-executor/tests skills/cli-detector/tests skills/config-reader/tests skills/sprint/tests skills/at-prompt-runner/tests scripts/tests; do
  python3 -m pytest "$suite" -q || exit 1
done

# Generated docs still in sync (executor is the registry consumer)
python3 scripts/manage-models.py check

# Entry point intact: help, model resolution, loop status
python3 skills/prompt-executor/scripts/executor.py --help | grep -q require-diff
python3 skills/prompt-executor/scripts/executor.py 009 --model codex | head -3
python3 skills/prompt-executor/scripts/executor.py --loop-status

# Facade intact: every historically-patched name still resolves on the executor module
python3 -c "
import sys; sys.path.insert(0, 'skills/prompt-executor/scripts')
import executor
for n in ['subprocess','shutil','Path','get_cli_info','run_cli','run_cli_foreground',
          'run_verification_loop','run_verification_loop_background','resolve_sandbox_config',
          'build_bwrap_args','sandbox_preflight','check_bwrap_available','repo_state_snapshot',
          'create_worktree','detect_default_branch','get_repo_root','get_cli_logs_dir',
          'get_loop_state_dir','wrap_prompt_with_verification_protocol','MODEL_SPECS',
          'MODEL_CHOICES','MODEL_REGISTRY_BY_NAME','LEGACY_MODEL_DISPLAY','INSTRUCTIONS_END_SENTINEL',
          'SANDBOX_ENV_PASSTHROUGH','_SANDBOX_PREFLIGHT_CACHE','_sandbox_passthrough_env']:
    assert hasattr(executor, n), f'MISSING FACADE ATTR: {n}'
print('facade OK:', 'all names resolve')
"
```

Do NOT add new behavioral tests — this is a refactor. The existing suite passing unchanged (modulo monkeypatch-target moves) IS the proof of correctness. A useful ADDITION: a small test that asserts the facade surface (the loop above) so future splits can't silently drop a re-export.
</verification>

<output>
- New modules under `./skills/prompt-executor/scripts/` (paths.py, repostate.py, worktree.py, models.py, sandbox.py, loop.py or your justified variant)
- `./skills/prompt-executor/scripts/executor.py` reduced to entry point + facade re-exports
- Minimal test patch-target updates in `./skills/prompt-executor/tests/` (assertions unchanged)
- Optional: `./skills/prompt-executor/tests/test_facade.py` pinning the re-export surface
- Report: `./prompts/reports/248-executor-split-report.md` — final module layout, dependency graph (prove no cycles), line-count before/after per module, the list of every monkeypatch target that had to move and why, and confirmation that no assertion changed
</output>

<success_criteria>
- executor.py drops from ~3,500 lines to a thin entry point + facade; each concern lives in its own module
- All six pytest suites pass (362+ tests); manage-models check passes; facade check passes
- git diff shows moved code is verbatim (only import lines added/changed) — reviewable as a move, not a rewrite
- Zero behavior change: same CLI output, same loop semantics, same sandbox commands
</success_criteria>