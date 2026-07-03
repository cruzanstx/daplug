<objective>
Make the model registry a single source of truth. Today, adding one model to daplug requires manually editing 14 places across 8 files (documented as the "Manual Checklist" in CLAUDE.md). This is a guaranteed drift generator — models are added almost every release (Synthetic, Antigravity, GLM-5.2 recently). Move the model definitions into one `scripts/models.json` file, make `executor.py` load it at runtime, and extend `scripts/manage-models.py` to regenerate the derived markdown sections instead of only checking them.
</objective>

<context>
This is the daplug Claude Code plugin repo. Read CLAUDE.md first — especially the "Managing Models" section, which lists all 14 derived locations, and the "Model Shorthand Reference" table.

Key files:
@skills/prompt-executor/scripts/executor.py — the `models = {...}` dict (~line 478 region) and the `--model` argparse choices (~line 3000 region)
@scripts/manage-models.py — existing list/check/add commands; extend this
@skills/prompt-executor/SKILL.md — `--model` options list + Model Reference table
@commands/run-prompt.md — `--model` argument description
@commands/prompts.md — preferred_agent options list
@commands/create-prompt.md — `<available_models>` section, recommendation table, 3 model selection menus
@commands/create-llms-txt.md — `<available_models>` section, recommendation table, model menu
@README.md — Model Tiers section
@CLAUDE.md — Model Shorthand Reference table + the Manual Checklist itself

Also examine @skills/cli-detector/scripts/router.py — if it duplicates model metadata, note the overlap in your final report but do NOT refactor it in this prompt; keep scope contained.
</context>

<requirements>
1. **Create `scripts/models.json`** containing every model currently in executor.py's `models` dict, with all fields (command, display, env, stdin_mode, cli routing, variant support, claude_model_flag, etc.). Preserve exact current behavior — this is a refactor, not a behavior change. Include per-model metadata needed by the markdown targets (family/tier grouping, description, quota notes) so docs can be generated.

2. **executor.py loads the registry at runtime** from models.json (resolve the path relative to the executor script's own location via the plugin layout, NOT the CWD — the executor runs from arbitrary directories and worktrees). The argparse `--model` choices must be derived from the loaded registry. Fail with a clear error if models.json is missing or malformed. No new third-party dependencies — stdlib json only.

3. **Extend `scripts/manage-models.py` with a `generate` command** that rewrites the derived sections in the markdown files (SKILL.md, run-prompt.md, prompts.md, create-prompt.md, create-llms-txt.md, README.md, CLAUDE.md). Use HTML marker comments around generated regions (e.g. `<!-- BEGIN GENERATED: model-shorthand-table -->` / `<!-- END GENERATED: model-shorthand-table -->`) so hand-written prose around them survives regeneration. The first `generate` run inserts the markers; subsequent runs replace only the content between them.

4. **`check` becomes a real verifier**: it must fail (non-zero exit) if running `generate` would change any file — i.e., generate to a temp copy and diff. This is what CI runs (.github/workflows/tests.yml already calls `python scripts/manage-models.py check` — keep that entry point working).

5. **`add` command** updates models.json (interactive as today), then runs `generate` automatically.

6. **Update CLAUDE.md's "Managing Models" section** to describe the new workflow (edit models.json → run generate) and shrink the manual checklist to the generated-marker model. Keep the Verification subsection working.
</requirements>

<implementation>
- Work in small steps: (a) extract dict → models.json + runtime loader with tests green, (b) build generate for one target file, (c) roll out to remaining targets, (d) rewire check, (e) docs.
- The generated markdown must match the *current* content semantically (same models, same descriptions) but need not preserve byte-identical prose — normalize formatting where the current files have drifted from each other. Where current files disagree about a model, treat executor.py's dict as truth and note the discrepancy in your final report.
- Do not silently drop any model, alias, or menu entry. If a checklist location turns out to be impractical to generate (deeply interwoven with prose), leave it hand-written, EXCLUDE it from check, and document why in the final report — do not fake coverage.
- Match existing code style in executor.py and manage-models.py (argparse subcommands, no external deps).
</implementation>

<verification>
All of these must pass before declaring completion:

```bash
# 1. Full test suites (same set CI runs)
for suite in skills/prompt-executor/tests skills/cli-detector/tests skills/config-reader/tests skills/sprint/tests skills/at-prompt-runner/tests scripts/tests; do
  python3 -m pytest "$suite" -q || exit 1
done

# 2. Registry consistency (the CI entry point)
python3 scripts/manage-models.py check

# 3. Idempotency: generate twice, second run changes nothing
python3 scripts/manage-models.py generate
git diff --exit-code

# 4. Executor still resolves every model
python3 skills/prompt-executor/scripts/executor.py --help | grep -q synthetic
python3 skills/prompt-executor/scripts/executor.py 001 --model codex | head -5
python3 skills/prompt-executor/scripts/executor.py 001 --model glm52 | head -5
```

New unit tests required (add to the appropriate existing test dirs):
- [ ] models.json loads and every model has required fields (schema-style validation test)
- [ ] executor's registry after the refactor contains the exact same model names as before (pin the full list of shorthand keys in the test)
- [ ] argparse rejects an unknown --model and accepts every registry key
- [ ] generate is idempotent (run twice on a temp copy, second run is a no-op)
- [ ] check fails when models.json has a model missing from a generated file, passes when in sync
- [ ] path resolution: registry loads correctly when CWD is not the repo root
</verification>

<output>
Modified/created files:
- `./scripts/models.json` — the single source of truth
- `./skills/prompt-executor/scripts/executor.py` — runtime loader replaces hardcoded dict
- `./scripts/manage-models.py` — generate/check/add rework
- Generated-marker updates in: `./skills/prompt-executor/SKILL.md`, `./commands/run-prompt.md`, `./commands/prompts.md`, `./commands/create-prompt.md`, `./commands/create-llms-txt.md`, `./README.md`, `./CLAUDE.md`
- New tests in `./scripts/tests/` and `./skills/prompt-executor/tests/`

Write a final report to `./prompts/reports/245-model-registry-report.md` covering: coverage map (which of the 14 checklist locations are now generated vs. still hand-written and why), any discrepancies found between the old files, and the router.py overlap observation.
</output>

<success_criteria>
- Adding a hypothetical new model requires editing ONLY models.json + running `python3 scripts/manage-models.py generate`
- `check` exits non-zero on any drift between models.json and generated content
- All six pytest suites pass; CI workflow needs no changes beyond what check already runs
- Zero behavior change for every existing model shorthand
</success_criteria>