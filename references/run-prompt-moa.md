# Run Prompt: Mixture of Agents (--moa)

> Reference for `commands/run-prompt.md`, moved verbatim so the main body stays under Antigravity's 24000-byte skill limit. Read it before launching any `--moa` run.

## Mixture of Agents (--moa)

`--moa model1,model2[,model3...]` runs the same prompt with multiple models in parallel, each in its own isolated worktree. When all runs finish, **you (the Claude Code session) act as the judge**: compare the diffs, run the tests in each worktree, and consolidate the best result onto one branch.

### Launch

```bash
python3 "$EXECUTOR" {PROMPT} --moa codex,synthetic,qwen36 --run [--loop] [--sandbox ...]
```

Rules enforced by the executor:
- Mutually exclusive with `--model` and the global `--cli`. Per-model CLI overrides use inline `model:cli` syntax instead: `--moa codex:opencode,qwen36` (aliases `cc`/`claudecode`/`antigravity` accepted; unsupported model+CLI combos error up front).
- The same model on different CLIs counts as two distinct runs: `--moa codex,codex:opencode` compares the Codex CLI against OpenCode. Each run's unique key ("label") is `model` or `model-cli`.
- Implies `--worktree` — one worktree + branch per run (`prompt/{slug}-moa-{label}`).
- `--variant` is applied per model where supported and silently dropped otherwise (`variant_dropped: true` in the run entry).
- `--loop` applies per runner; loop state is keyed per run: `~/.claude/loop-state/{N}-moa-{label}.json`.

**CLI override caveat:** `codex:opencode` routes GPT-5.5 through OpenCode's `openai` provider, which typically authenticates with an OpenAI API key rather than the ChatGPT/Codex subscription — quota/billing may differ from a plain `codex` run.

**Cost note:** MoA multiplies quota usage by the number of models. If `ai_usage_awareness` is enabled, consider a quick `/daplug:ai-usage` check before launching a 3+ model fan-out.

### JSON Output

Top-level: `model: "moa"`, `moa_models: [...]`. Per prompt, `prompts[].moa`:
- `manifest_file` - persisted manifest at `~/.claude/loop-state/moa/{N}-{timestamp}.json` (the judge phase reads this)
- `runs[]` - one entry per run: `model`, `cli` (per-entry override or null), `label`, `status`, `worktree_path`, `branch_name`, `log`, `state_file` (loop mode), `execution`, `variant`, `variant_dropped`
- Per-run `status`: `running` / `loop_running` (launched), `conflict` (worktree exists — handle like the single-model conflict flow, per run), `error` (that run failed; others continue), `info` (no `--run`)

### Monitoring

Spawn ONE monitor per model run (same pattern as Step 2 Part B), pointing at each run's `log` (and `state_file` when `--loop`). When every monitor reports a terminal state, proceed to the judge phase.

### Judge & Consolidation Phase (you do this)

When all runs complete:

1. **Collect**: Read the manifest, then for each worktree: `git -C {worktree_path} diff {base_branch} --stat` and the full diff.
2. **Verify**: Run the project's tests/build in each worktree. Record pass/fail.
3. **Score**: Compare on correctness (tests pass), completeness vs the prompt, code quality/fit with the codebase, and scope discipline (no unrelated changes).
4. **Report**: Show the user a scorecard table (model, tests, diff size, notable strengths/weaknesses) and your recommendation.
5. **Consolidate** (after user picks, or immediately if the user pre-authorized): merge the winning branch; optionally cherry-pick superior pieces from the other worktrees onto it. Delete `TASK.md` before merging.
6. **Attribute**: Credit contributing agents in the merge commit footer per the user's commit conventions (e.g. `Co-Authored-By: Codex <noreply@openai.com>`).
7. **Cleanup**: After merge, remove the losing worktrees/branches (ask first if the user may want to inspect them).

