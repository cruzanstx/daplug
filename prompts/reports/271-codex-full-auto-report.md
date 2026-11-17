# 271 — Codex `--full-auto` removal fix

codex-cli 0.167.0 removed `codex exec --full-auto`, so every daplug Codex route
failed with `error: unexpected argument '--full-auto' found` (exit 2).

## Before / after argv (codex-high)

Before:
```
["codex", "exec", "--full-auto", "-m", "gpt-5.6-terra", "-c", "model_reasoning_effort=\"high\"", "-"]
```

After (from `executor.py 001 --model codex-high --cli codex` in a throwaway git repo):
```
["codex", "exec", "--sandbox", "workspace-write", "--approve-for-me", "-m", "gpt-5.6-terra", "-c", "model_reasoning_effort=\"high\"", "-"]
```

Legacy Codex (probe says `--approve-for-me` is missing), at launch:
```
["codex", "exec", "--full-auto", "-m", "gpt-5.6-terra", "-c", "model_reasoning_effort=\"high\"", "-"]
```

## What changed

- `skills/prompt-executor/scripts/models.py`: new `CODEX_UNATTENDED_FLAGS`,
  `codex_supports_approve_for_me()` (probe) and `apply_codex_compat()` (rewrite).
  `_build_codex_command` now emits the modern flags.
- `skills/prompt-executor/scripts/loop.py`: `run_cli` and `run_cli_foreground`
  call `apply_codex_compat(base_command)` right after the Claude permission
  adjustment. This is the only spot where `--full-auto` can come back.
- `scripts/models.json`: all codex/gpt5x/terra/spark/sol/luna/astra/zai `command`
  arrays and `reference_cli` strings were updated. `scripts/manage-models.py`
  `default_command` was updated to match, and `generate` was re-run (it
  regenerated `skills/prompt-executor/SKILL.md`). `manage-models.py check`
  reports "in sync".
- `skills/cli-detector/scripts/router.py` and `plugins/codex.py` now emit the
  modern flags. Router commands go through the same `loop.run_cli*` launch path,
  so they get the fallback too.
- Docs: CLAUDE.md, README.md, commands/{codex,zai,qwen,devstral}-cli.md,
  docs/agent-detection-*.md, prompt-executor SKILL.md and the cli-detector
  templates README.
- Tests: the old argv assertions now expect the new flags. New file:
  `skills/prompt-executor/tests/test_codex_compat.py`.
- Not touched: `--dangerously-bypass-approvals-and-sandbox` and all bwrap logic.

## Probe design

- `codex_supports_approve_for_me(codex_bin="codex")` is wrapped in
  `functools.lru_cache`, so it runs at most once per process (per binary). It
  runs `codex exec --help` with a 15s timeout and returns whether the help text
  contains `--approve-for-me`.
- It returns False, which triggers the legacy `--full-auto`, **only** when the
  help call succeeded (rc 0, output contains "usage") and the flag is absent.
  If the probe fails (binary missing, timeout, non-zero exit), it keeps the
  modern flags, and the real launch reports the real error.
- Hot path: command building (`get_cli_info`, `--info-only`, router resolution)
  never probes. The probe only runs lazily inside `apply_codex_compat` at
  launch time, and only for `codex exec` argv that contain the modern flag
  triple. Tests cover this: non-codex/bypass commands and `get_cli_info` with a
  probe that raises.
- Unit tests monkeypatch the probe to cover both branches (True → modern,
  False → `--full-auto`). They also check the probe itself against faked help
  output for new and old Codex, its caching (one subprocess call), and the
  behaviour on probe failure.

## Verification

- `bash scripts/run-tests.sh`: all suites pass (prompt-executor 407 passed /
  3 skipped; cli-detector 217 passed / 1 skipped; config-reader, handoff,
  sprint, at-prompt-runner, scripts/tests all pass). Registry check: "Generated
  model documentation is in sync." `test_executor_markers.py`: 18 passed.
- `--full-auto` remaining outside the fallback and its tests: the
  `CODEX_LEGACY_UNATTENDED_FLAG` constant and comment in models.py,
  `test_codex_compat.py`, one explanatory note in
  `skills/cli-detector/templates/README.md`, TASK.md, and archived
  `prompts/completed/**` records. The archived records were left as historical
  documents.

### Smoke test

Run from a throwaway repo (`T=$(mktemp -d); git -C $T init -q`):

- The argv shown in "After" above came from the executor.
- `codex exec --approve-for-me -m gpt-5.6-terra -c 'model_reasoning_effort="high"' "reply OK"`:
  ```
  (eval):1: command not found: codex
  exit=127
  ```
  The agent's bwrap sandbox does not mount the Codex install
  (`/usr/local/bin/codex -> /root/.bun/bin/codex`, and `/root/.bun` is absent).
  So the live Codex session **could not be verified from inside this run**.
  `$T` was removed.

To verify on the host, run:
`T=$(mktemp -d); git -C $T init -q; (cd $T && codex exec --approve-for-me -m gpt-5.6-terra "reply OK"; echo exit=$?); rm -rf $T`

## Commit

The worktree's gitdir (`/storage/projects/docker/daplug/.git/worktrees/...`)
is not mounted in this sandbox, so `git` fails with "not a git repository".
The atomic commit
`fix(codex): replace removed --full-auto with --approve-for-me`
has to be created from the host. All changes are in the worktree.

## Iteration 3 re-check (2026-11-17)

- `pytest`: 816 passed, 4 skipped. `manage-models.py check`: in sync.
- Blockers unchanged: `git` still reports "not a git repository" because the gitdir isn't mounted, and `/usr/local/bin/codex` is a dangling symlink to `/root/.bun/bin/codex`.
- The commit and the live smoke test still have to be done from the host.

## Parent correction (host)

The prompt specified `--sandbox workspace-write --approve-for-me`. codex-cli 0.167.0 rejects that pair (`the argument '--sandbox <SANDBOX_MODE>' cannot be used with '--approve-for-me'`, exit 2). `--approve-for-me` already implies the workspace-write sandbox, so the unattended flags are now just `["--approve-for-me"]`. Tests were updated to match: 819 passed, 1 skipped.

Host smoke test (fresh `git init` temp repo, stdin mode, the exact codex-high argv built by the executor):
`codex exec --approve-for-me -m gpt-5.6-terra -c 'model_reasoning_effort="high"' -` printed exit=0 and `DONE`, and wrote `ok.txt` containing `OK`.
