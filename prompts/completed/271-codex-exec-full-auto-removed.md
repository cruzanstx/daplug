<objective>
Fix every daplug Codex route. codex-cli 0.167.0 removed `--full-auto` from `codex exec`, so each `--cli codex` run now dies in under a second:

```
error: unexpected argument '--full-auto' found
Usage: codex exec [OPTIONS] [PROMPT]
```

(Observed: prompt 270, model codex-high, 3/3 iterations exit 2, log ~/.claude/cli-logs/codex-high-270-iter1-20261116-194831.log.)
</objective>

<context>
Read CLAUDE.md for repo conventions.

`--full-auto` used to mean workspace-write sandbox plus no approval prompts. The current `codex exec --help` (0.167.0) offers:
- `-s, --sandbox <read-only|workspace-write|danger-full-access>`
- `--approve-for-me`: route approval requests through automatic review, using the workspace-write sandbox
- `--dangerously-bypass-approvals-and-sandbox`

Where `--full-auto` lives today (find every one with `git grep -n -- --full-auto`):
- skills/prompt-executor/scripts/models.py:382 `cmd = ["codex", "exec", "--full-auto"]`
- scripts/models.json: the `command` arrays and `reference_cli` strings for the codex/gpt5x/terra/spark/sol/luna/astra families
- skills/prompt-executor/scripts/test_executor_markers.py:225 and any other tests that assert the old argv
- docs/commands that print example codex command lines
</context>

<requirements>
1. Replace `--full-auto` with `--sandbox workspace-write --approve-for-me` everywhere it builds or documents a `codex exec` command. That pair is the closest equivalent: same sandbox, unattended.
2. Back-compat: detect support once per process by checking `codex exec --help` output for `--approve-for-me`, cached. Fall back to `--full-auto` only when the new flag is absent (older Codex). Keep the probe out of the hot path, and unit test both branches by monkeypatching the probe.
3. Do not touch the `--dangerously-bypass-approvals-and-sandbox` path or any bwrap logic.
4. Keep `scripts/models.json` and `models.py` consistent, and run the repo's model-registry/manage-models consistency check.
5. Update the test assertions to the new argv.
</requirements>

<verification>
- Full pytest suite passes.
- `git grep -n -- --full-auto` shows only the fallback branch and its test.
- Real smoke test, run from a throwaway git repo (`T=$(mktemp -d); git -C $T init -q`): build the codex-high command via the executor's `--info-only` (or equivalent) and confirm the argv. Then execute `codex exec --sandbox workspace-write --approve-for-me -m <codex-high model> "reply OK"` in $T and paste the exit code and first lines in the report. Remove $T.
</verification>

<output>
- Atomic commit: `fix(codex): replace removed --full-auto with --sandbox workspace-write --approve-for-me`
- Report: `prompts/reports/271-codex-full-auto-report.md` with the before/after argv, the probe design and the smoke output.
- No version bump or release.
</output>

<success_criteria>
- `daplug-run <n> --cli codex --model codex-high --run` launches a real Codex session on codex-cli 0.167.0.
- Older Codex still gets `--full-auto`.
</success_criteria>
