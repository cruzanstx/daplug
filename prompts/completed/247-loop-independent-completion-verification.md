<objective>
Make `--loop` completion trustworthy. Today the loop's only success signal is the model's self-reported `<verification>VERIFICATION_COMPLETE</verification>` marker, and GitHub issues #14 and #18 prove that is not enough:

- Issue #14: a 530-line migration prompt reached VERIFICATION_COMPLETE on iteration 3 with ZERO edit/write tool calls across all iterations — the final summary claimed patches were applied but nothing existed on disk. Silent false success.
- Issue #18: a prompt with a mandatory read-gate on an absolute path outside the isolated worktree correctly refused to proceed, but the loop treated that as retryable and burned iterations on a failure that no retry could ever fix. Wasted work with no state change possible.

Add two independent checks to the loop in executor.py: (1) an opt-in `--require-diff` flag that refuses to accept the completion marker when the execution directory has no file changes, and (2) automatic dead-loop detection that aborts early when retry reasons show the loop cannot make progress.
</objective>

<context>
This is the daplug Claude Code plugin repo. Read CLAUDE.md for conventions.

Key code:
@skills/prompt-executor/scripts/executor.py — `run_verification_loop()` (~line 2650 region) is the loop core: it runs iterations via `run_cli_foreground()`, scans logs for the completion marker, records history entries with `retry_reason`, and persists state to ~/.claude/loop-state/{N}.json. Also relevant: `repo_state_snapshot()` (content-hash based dirty tracking, built for the #20 fix — reuse its approach), `wrap_prompt_with_verification_protocol()` (injects the protocol text the model sees), and the argparse setup in `main()`.
@skills/prompt-executor/tests/test_worktree_isolation.py and test_sandbox.py — existing loop test patterns (they monkeypatch run_cli_foreground and drive the loop with fake exec results; follow that style).

Read GitHub issues #14 and #18 in full for the failure narratives:
  gh issue view 14 --repo cruzanstx/daplug
  gh issue view 18 --repo cruzanstx/daplug
</context>

<requirements>
1. **`--require-diff` flag** (opt-in, off by default):
   - When enabled and the completion marker is found, verify the execution cwd (worktree when `--worktree`, else repo) actually changed: uncommitted tracked modifications, untracked files, OR commits made since the loop started (agents sometimes commit their work — count `git log` since a start ref captured at loop begin). Exclude executor-injected artifacts: TASK.md and .sisyphus/.
   - If the marker is present but nothing changed: do NOT accept completion. Record a history entry with a synthetic retry_reason (e.g. "completion marker found but no file changes detected (--require-diff)"), inject that feedback into the next iteration's wrapped prompt so the model sees why it was rejected, and continue the loop.
   - If this happens on the final iteration, the loop must end with a distinct terminal status (e.g. "completed_unverified") — NOT "completed" — so callers and monitors can tell the difference.
   - Thread the flag through: argparse in main(), loop launch paths (foreground and background re-entry — background mode re-invokes executor.py with CLI args, so the flag must survive that round trip; see how --worktree-path is forwarded), state file, and JSON output.

2. **Dead-loop detection** (always on, no flag):
   - If two consecutive iterations end with the same normalized retry_reason (case/whitespace-insensitive), abort with terminal status "stalled" and a failure_reason explaining that repeated identical retry reasons indicate no progress is possible.
   - Additionally, if a retry_reason matches impossible-gate patterns — references to paths outside the worktree / isolation boundary refusals (e.g. contains "outside the isolated worktree", "isolation boundary", "cannot read" + an absolute path not under the execution cwd) — abort immediately after the FIRST occurrence with terminal status "blocked" and a suggested next step ("the prompt requires resources unavailable under --worktree isolation; re-run without --worktree or copy the required file into the repo").
   - Both statuses must persist to the state file and appear in the loop log and JSON result.

3. **Protocol text update**: `wrap_prompt_with_verification_protocol()` should tell the model (when --require-diff is active) that completion claims are independently verified against the file system, and that a NEEDS_RETRY reason which cannot change between iterations should instead be reported as a blocking condition.

4. **Docs**: update commands/run-prompt.md arguments table and skills/prompt-executor/SKILL.md for the new flag and the new terminal statuses. If those sections are inside generated marker regions, update the generator source in scripts/manage-models.py ONLY if model-related; otherwise edit the hand-written sections directly. Run `python3 scripts/manage-models.py check` to ensure you did not break generated regions.

5. Zero behavior change when --require-diff is absent and retry reasons vary — existing loop tests must pass unmodified.
</requirements>

<verification>
```bash
for suite in skills/prompt-executor/tests skills/cli-detector/tests skills/config-reader/tests skills/sprint/tests skills/at-prompt-runner/tests scripts/tests; do
  python3 -m pytest "$suite" -q || exit 1
done
python3 scripts/manage-models.py check
python3 skills/prompt-executor/scripts/executor.py --help | grep -q require-diff
```

New unit tests required (follow the existing monkeypatched-loop style):
- [ ] marker + no changes + --require-diff → loop continues with synthetic retry_reason; final-iteration case ends "completed_unverified"
- [ ] marker + real file change + --require-diff → "completed"
- [ ] marker + committed-but-clean worktree + --require-diff → "completed" (commits count as changes)
- [ ] TASK.md/.sisyphus-only changes do NOT count as changes
- [ ] two identical consecutive retry_reasons → "stalled"
- [ ] isolation-refusal retry_reason → "blocked" after first occurrence, with suggested next step
- [ ] --require-diff survives the background re-entry round trip (flag forwarding test, mirroring the existing --worktree-path forwarding regression test)
- [ ] no flag, varying retry reasons → existing behavior unchanged
</verification>

<output>
- Modified: `./skills/prompt-executor/scripts/executor.py`, `./commands/run-prompt.md`, `./skills/prompt-executor/SKILL.md`
- New tests in `./skills/prompt-executor/tests/` (new file test_loop_verification.py or extend existing)
- Report: `./prompts/reports/247-loop-verification-report.md` — design decisions, how each of #14/#18 would have played out under the new behavior (walk through their timelines), and any edge cases deliberately left out
</output>

<success_criteria>
- Replaying issue #14's scenario (marker on final iteration, zero changes) with --require-diff ends in "completed_unverified", not silent success
- Replaying issue #18's scenario (isolation-refusal retry reason) aborts as "blocked" after iteration 1 instead of burning all iterations
- All six pytest suites pass; manage-models check passes; default loop behavior byte-identical for well-behaved runs
</success_criteria>