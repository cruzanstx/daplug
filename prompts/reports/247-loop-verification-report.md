# Loop Verification Enhancement: --require-diff and Dead-Loop Detection

**Prompt:** 247  
**Date:** 2026-07-03  
**Issues addressed:** #14 (silent false success), #18 (wasted iterations on impossible gates)

## Summary

Two independent safeguards were added to `run_verification_loop()` in `executor.py`:

1. **`--require-diff` flag** (opt-in): refuses to accept the completion marker when the execution directory has no file changes, converting the false success into a retry or a distinct `completed_unverified` terminal status.

2. **Dead-loop detection** (always on): aborts early when retry reasons indicate no progress is possible, either because the same reason repeats (`stalled`) or because the reason references resources outside the worktree boundary (`blocked`).

## Design Decisions

### --require-diff

**What counts as a change.** Three signals are checked in combination:
- Uncommitted tracked modifications (via `repo_state_delta` — the existing content-hash snapshot system built for the #20 fix)
- New or removed untracked files (same system)
- Commits made since the loop started (via `git rev-parse HEAD` comparison — agents sometimes commit their work, leaving the tree clean)

**What does NOT count.** `TASK.md` and `.sisyphus/` are executor-injected artifacts. A change limited to these paths is treated as "no change" so the loop doesn't falsely accept completion just because the executor wrote a task file.

**Rejection flow.** When the marker is found but no diff is detected:
1. `marker_found` is overridden to `False`
2. A synthetic `retry_reason` ("completion marker found but no file changes detected (--require-diff)") is set
3. The rejection is logged to both stderr and the loop log
4. The history entry records `marker_found: false` and the synthetic reason
5. The next iteration's wrapped prompt includes this feedback via `build_previous_iteration_feedback`

**Terminal status on final iteration.** If the diff rejection happens on the last iteration (and the stalled detection doesn't fire first), the loop ends with `completed_unverified` — distinct from both `completed` and `max_iterations_reached`.

**Start state persistence.** The baseline snapshot (`start_snapshot`) and HEAD ref (`start_head`) are captured at loop start and stored in the state file, so they survive across resumes. If the state was created by an older version without these fields, they are captured at resume time (best-effort).

**Why opt-in.** The default loop behavior is byte-identical for well-behaved runs. Users who want the extra safety net add `--require-diff`; everyone else gets the same loop they had before.

### Dead-loop detection

**Stalled (two consecutive identical retry reasons).** Normalized via `" ".join(reason.lower().split())` — case-insensitive and whitespace-insensitive. Fires on the second occurrence, not the first, to allow the model a chance to fix a transient issue. The status is `stalled` with a `failure_reason` explaining the repetition.

**Blocked (impossible-gate patterns).** Fires on the FIRST occurrence — no point in waiting for a second. Matches:
- The literal phrase "outside the isolated worktree"
- The literal phrase "isolation boundary"
- "cannot read" or "can't read" combined with an absolute path not under the execution cwd

When triggered, the status is `blocked` and a suggested next step is appended: "the prompt requires resources unavailable under --worktree isolation; re-run without --worktree or copy the required file into the repo."

**Priority order.** `blocked` (impossible gate) is checked before `stalled` (repeated reason), which is checked before `max_iterations_reached` / `completed_unverified`. This ensures the most informative status wins.

**Interaction with --require-diff.** If the model claims completion twice without any diff, the synthetic retry reasons are identical, and the stalled detection fires on the second iteration. This means a `#14`-style scenario with `--require-diff` and `max_iterations >= 2` ends as `stalled`, not `completed_unverified` — which is the more informative status.

### Protocol text

When `--require-diff` is active, `wrap_prompt_with_verification_protocol()` adds two lines to the verification protocol:
- Completion claims are independently verified against the file system and will be rejected if no file changes are detected.
- A NEEDS_RETRY reason that cannot change between iterations should be reported as a blocking condition.

## Issue #14 Walkthrough

**Original scenario:** A 530-line migration prompt reached VERIFICATION_COMPLETE on iteration 3 with zero edit/write tool calls across all iterations. The final summary claimed patches were applied but nothing existed on disk.

**Under the new behavior with `--require-diff`:**

| Iteration | Marker | Diff? | Action | Status |
|-----------|--------|-------|--------|--------|
| 1 | Yes | No | Rejected; synthetic retry reason injected | running |
| 2 | Yes | No | Rejected; same synthetic retry reason | **stalled** (two consecutive identical) |

The loop aborts after iteration 2 with status `stalled` and a failure reason explaining the repeated identical retry reasons. The operator sees the loop did not complete and knows the model's completion claims were not backed by file changes.

**With `max_iterations=1` and `--require-diff`:** The single iteration's marker is rejected, and since there are no more iterations, the loop ends with `completed_unverified`.

**Without `--require-diff`:** The behavior is unchanged — the marker is accepted and the loop completes (the original bug).

## Issue #18 Walkthrough

**Original scenario:** A prompt with a mandatory read-gate on an absolute path outside the worktree correctly refused to proceed. The loop treated this as retryable and burned all iterations.

**Under the new behavior (no flag needed):**

| Iteration | Retry reason | Detection | Action | Status |
|-----------|-------------|-----------|--------|--------|
| 1 | "cannot read /storage/projects/original/config.yaml: outside the isolated worktree" | Impossible gate matched | **blocked** | aborted |

The loop aborts after iteration 1 with status `blocked`, a failure reason explaining the impossible gate, and a suggested next step telling the operator to re-run without `--worktree` or copy the required file into the repo.

## Tests

19 new tests in `test_loop_verification.py`:

- `test_require_diff_marker_no_changes_final_iteration_completed_unverified` — marker + no diff + final iteration → `completed_unverified`
- `test_require_diff_marker_no_changes_continues_with_synthetic_retry` — marker + no diff + multi-iteration → `stalled` (two consecutive identical synthetic reasons)
- `test_require_diff_marker_real_file_change_completed` — marker + new untracked file → `completed`
- `test_require_diff_marker_modified_tracked_file_completed` — marker + modified tracked file → `completed`
- `test_require_diff_marker_committed_but_clean_completed` — marker + committed work → `completed` (commits count)
- `test_require_diff_task_md_only_does_not_count` — TASK.md only → `completed_unverified`
- `test_require_diff_sisyphus_only_does_not_count` — .sisyphus/ only → `completed_unverified`
- `test_require_diff_real_file_alongside_task_md_counts` — TASK.md + real file → `completed`
- `test_stalled_two_identical_retry_reasons` — two identical reasons → `stalled`
- `test_stalled_case_insensitive_comparison` — case/whitespace variation → `stalled`
- `test_blocked_isolation_boundary_refusal` — "outside the isolated worktree" → `blocked`
- `test_blocked_cannot_read_outside_path` — "cannot read /etc/passwd" → `blocked`
- `test_blocked_isolation_boundary_phrase` — "isolation boundary" → `blocked`
- `test_no_flag_varying_retry_reasons_no_stall` — varying reasons, no flag → `max_iterations_reached`
- `test_no_flag_marker_no_diff_still_completes` — no flag, marker + no diff → `completed` (backward compat)
- `test_require_diff_forwarded_in_background_reentry` — `--require-diff` in spawned command
- `test_require_diff_absent_when_not_set_in_background` — `--require-diff` NOT in spawned command when not set
- `test_wrap_prompt_includes_diff_warning_when_require_diff` — protocol text includes diff warning
- `test_wrap_prompt_omits_diff_warning_when_no_require_diff` — protocol text omits diff warning

## Edge Cases Deliberately Left Out

1. **Non-git execution cwd.** `repo_state_snapshot` and `_get_git_head` return empty/None outside a git repo. The diff check would report no changes. This is acceptable because `--require-diff` is designed for code tasks in git repos, and the execution cwd is always either the repo or a worktree.

2. **Binary file changes.** `repo_state_snapshot` uses `git hash-object` which handles binary files correctly, so binary diffs are detected. But the diff check doesn't inspect file *content* — any change counts, even a whitespace-only edit. This is intentional: the point is to detect whether the agent *did* anything, not whether the change is semantically meaningful.

3. **Staged but uncommitted changes.** `git ls-files -m` detects staged changes (they show as modified). The snapshot captures this. But if the agent stages a change and then resets it, the before/after snapshots would match and no diff would be detected. This is correct: if nothing changed, nothing changed.

4. **Concurrent modifications by other processes.** If another process modifies files in the execution cwd during the loop, those changes would be detected by the diff check. This could lead to a false positive (accepting completion when the agent didn't actually make the change). This is acceptable because the execution cwd is either the repo (shared) or an isolated worktree (not shared), and the `--require-diff` flag is opt-in.

5. **Retry reason normalization depth.** The stalled detection normalizes by lowercasing and collapsing whitespace, but does not perform stemming or synonym matching. "tests failing" and "test failures" would not be considered identical. This is intentional to avoid false positives — exact repetition is a much stronger signal than semantic similarity.
