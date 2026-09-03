<objective>
Add daplug support for Claude Fable 5.1 by adding an explicit pinned model shorthand `fable51` alongside the existing floating `fable` shorthand, following the exact "floating alias + explicit pin" convention daplug already uses for `glm5`/`glm52`/`glm53`. Leave an atomic, verified, **uncommitted** implementation in this worktree for independent review — do not commit, merge, push, tag, release, or deploy.

This matters because Claude Code v2.1.255+ (this host runs 2.1.259) now resolves the `fable` alias to Fable 5.1 automatically via native Claude CLI resolution — daplug's existing `fable` shorthand already tracks this correctly with zero code changes needed. What's missing is an explicit, version-pinned shorthand for callers who want Fable 5.1 specifically, regardless of what `fable` resolves to in the future (mirroring why `glm52`/`glm53` exist alongside the floating `glm5`).
</objective>

<authoritative_evidence>
Do NOT re-derive these facts or make any live API/network calls to verify them — treat them as given and cite them in code comments/changelog where the existing style does so (see `syn-glm53-flash` changelog entry for the citation style to match):

1. https://docs.anthropic.com/en/docs/claude-code/model-config — Claude Code v2.1.255+ resolves the alias `fable` to Fable 5.1 unless `ANTHROPIC_DEFAULT_FABLE_MODEL` overrides it. This host is Claude Code 2.1.259 with no such override set (confirm with `claude --version` and `echo $ANTHROPIC_DEFAULT_FABLE_MODEL` — expect empty).
2. https://platform.claude.com/docs/en/models/fable-5-1/overview — Canonical Claude API model ID: `claude-fable-5-1`. Released 2026-09-01. 1M context window, 128K max output tokens, $10/MTok input, $50/MTok output, adaptive thinking, effort levels low/medium/high/xhigh/max.

No API smoke calls, no paid credits spent verifying model behavior — this is a registry/plumbing change, not a runtime behavior change.
</authoritative_evidence>

<context>
Repo: daplug (Claude Code plugin). The dispatcher starts from `/storage/projects/docker/worktrees/daplug-integration-fable51-20260903` on branch `integration/fable51-wip-20260903` and, with the project defaults, creates a dedicated executor worktree. Make implementation changes only in that executor worktree.

Provenance (do not disturb): fetched base was `origin/main` = v0.40.6 at commit `4c0aac8d0bc2eb0b769150cd2f05e2ba7091c6da`. Current HEAD `6931447092304a6fec2e8901fb63240b719b8a40` adds independently-reviewed session-transcript WIP (`feat(prompts): reference creating Claude sessions`) — this is already reviewed and must not be touched, reverted, or re-reviewed by you.

Read before editing:
@scripts/models.json — single source of truth for model shorthands (`model_order_note` field says so explicitly). Read the full `fable` entry (currently `name: "fable"`, `model_id: "anthropic:fable"`, `claude_model_flag: "fable"`, `command` ends in `--model fable`) and the `glm5`/`glm52`/`glm53` entries as your structural template for the floating-alias-vs-explicit-pin pattern.
@scripts/manage-models.py — read `REQUIRED_MODEL_FIELDS` and `REQUIRED_DOC_FIELDS` constants (top of file) for every field a new registry entry must carry, and the `generate`/`check` subcommands.
@scripts/tests/test_manage_models.py — read `test_flash_and_glm53_flash_registry_entries` and `test_syn_glm53_flash_registry_entry` as templates for the registry-entry assertions you'll write for `fable51`.
@skills/cli-detector/tests/test_registry_consistency.py — read the `flash`/`glm53-flash` and `glm52`/`glm53` test classes (search `glm53_still_targets_glm_5_3`, the `("glm52", "glm-5.2")` / `("glm53", "glm-5.3")` parametrized cases near line 839) as templates for `fable51` router-consistency assertions.
@skills/cli-detector/tests/test_router.py — same parametrized-case pattern, search for `glm52`/`glm53` entries.
@CHANGELOG.md — read the `[Unreleased]` section's `syn-glm53-flash` and `flash`/`glm53-flash` entries as the exact prose/citation style to match for your new entry.
@CLAUDE.md — Model Shorthand Reference table (generated region) and the "Generated Locations" table (14 numbered rows) listing every file `manage-models.py generate` touches.

Do not read or modify anything under `prompts/completed/`, and do not touch files outside the dedicated executor worktree.
</context>

<requirements>
1. **Do not change the existing `fable` entry's routing.** It already produces `claude --print ... --model fable`, which is correct and already tracks Fable 5.1 per the authoritative evidence — Claude Code resolves the alias natively. Confirm this in your findings but make no code change to it.

2. **Add exactly one new registry entry: `fable51`.** Insert it in `scripts/models.json` immediately after the `fable` entry (matching how `glm52` sits immediately after `glm5`, `glm53` after `glm52`). It must:
   - `name`: `"fable51"`
   - `model_id`: reflect the canonical Claude API ID `claude-fable-5-1` (match the `model_id` convention `fable` uses today, e.g. `anthropic:claude-fable-5-1` — check the `anthropic:` prefix convention against the `fable`/`cc-sonnet`/`cc-opus` entries and follow it exactly)
   - `default_cli`: `"claude"` (same as `fable`)
   - `claude_model_flag`: `"claude-fable-5-1"` — this is the field that must make the generated CLI command read `--model claude-fable-5-1`
   - `command`: same shape as `fable`'s command array but with `"claude-fable-5-1"` as the final `--model` argument value
   - `routing`: same as `fable`'s (`cli_overrides: ["claude"]`, `force_direct_opencode: false`, `google: false`, `synthetic: false`)
   - `alias_of`: `null` (it is an independent pinned entry, not a versioned alias of `fable` — mirror `glm52`/`glm53`, which are also independent entries, not `alias_of` each other or `glm5`)
   - `docs`: fill every field in `REQUIRED_DOC_FIELDS`. Use the authoritative evidence for `actual_model`/`best_for`/`option_description` (mention 1M context, 128K max output, adaptive thinking, effort levels, pricing, and that it's an explicit pin vs the floating `fable`). Follow `glm52`'s docs block as the tone/structure template for an "explicit pin" entry (`readme_model`, `menu_note`, etc. should read as an explicit-pin sibling of `fable`, the way `glm52`'s docs read as an explicit-pin sibling of `glm5`).
   - Every field required by `REQUIRED_MODEL_FIELDS` in `scripts/manage-models.py` must be present — check the full set, not just the fields called out above (`supports_codex_reasoning`, `codex_profile`, `default_variant`, `env`, `stdin_mode` are also required; set them to match `fable`'s values).

3. **Do NOT add `fable5-1`** or any second spelling. Only `fable` (unchanged) and `fable51` (new) should exist.

4. **Regenerate all derived docs from the registry** — do not hand-edit any generated region:
   ```bash
   python3 scripts/manage-models.py generate
   python3 scripts/manage-models.py check
   ```
   `check` must exit 0 (no diff). This updates the 14 generated locations listed in `CLAUDE.md`'s "Generated Locations" table (executor.py argparse choices, SKILL.md tables, README.md Model Tiers, command markdown menus, CLAUDE.md's own shorthand table, etc.) — verify with `git status`/`git diff --stat` that only files consistent with that table changed, plus `scripts/models.json` itself.

5. **Add a `[Unreleased]` CHANGELOG.md entry** under `### Added`, in the same prose/citation style as the existing `syn-glm53-flash` and `flash`/`glm53-flash` entries in that section (cite the two authoritative URLs, state the pricing/context/output facts, and explicitly state that `fable` is unchanged and continues to float to whatever Claude Code resolves the `fable` alias to).

6. **Add focused tests** (do not modify unrelated existing tests):
   - In `scripts/tests/test_manage_models.py`: a test mirroring `test_flash_and_glm53_flash_registry_entries`/`test_syn_glm53_flash_registry_entry` that asserts the `fable51` registry entry has `claude_model_flag == "claude-fable-5-1"`, `command` ends with `["--model", "claude-fable-5-1"]`, `default_cli == "claude"`, `alias_of is None`, and that the pre-existing `fable` entry's `command` is unchanged (still ends with `["--model", "fable"]`) — this last assertion is the regression guard proving you didn't touch `fable`'s routing.
   - In `skills/cli-detector/tests/test_registry_consistency.py`: a test mirroring the `glm52`/`glm53` parametrized case (near the `("glm52", "glm-5.2")` pattern, adapted for Claude/`claude_model_flag` instead of `model_id`/Z.AI) asserting `router._SHORTHAND["fable51"]` resolves with the correct `claude_model_flag`/model reference and that `router._SHORTHAND["fable"]` is untouched.
   - In `skills/cli-detector/tests/test_router.py`: extend the existing parametrized table (the one containing `("glm52", "glm-5.2")`, `("glm53", "glm-5.3")`) with a `("fable51", "claude-fable-5-1")`-shaped case if the table's shape fits a Claude entry; otherwise add a small standalone test next to it following the same naming convention. If `fable` is already covered by an equivalent existing test, add the sibling case for `fable51` there instead of duplicating scaffolding.

   Keep these additions minimal and scoped — do not write a broad new test file or restructure existing test classes.
</requirements>

<verification>
Run each of these and capture the actual output (not a paraphrase) to include in your final report:

1. `python3 scripts/manage-models.py generate && python3 scripts/manage-models.py check` — `check` must exit 0.
2. `git status --porcelain` and `git diff --stat` — review the file list against `CLAUDE.md`'s Generated Locations table; nothing outside the registry + the 14 generated locations + your new/changed test files + CHANGELOG.md should appear.
3. Focused tests only (fast, targeted — not the full suite yet):
   ```bash
   python3 -m pytest scripts/tests/test_manage_models.py -v
   python3 -m pytest skills/cli-detector/tests/test_registry_consistency.py -v
   python3 -m pytest skills/cli-detector/tests/test_router.py -v
   ```
   All must pass, including your new cases.
4. Dry-run command generation proving the two shorthands diverge correctly (no live API calls — these just print the resolved command):
   ```bash
   python3 skills/prompt-executor/scripts/executor.py 001 --model fable
   python3 skills/prompt-executor/scripts/executor.py 001 --model fable51
   ```
   Confirm in your report that the `fable` output contains `--model fable` and the `fable51` output contains `--model claude-fable-5-1`. If prompt `001` doesn't exist in this worktree, use whatever existing prompt number the executor's info/dry-run mode accepts without executing a real model call — do not create a new prompt file just to satisfy this check.
5. Full suite: `python3 -m pytest -q` from repo root. All tests must pass. Report the final summary line verbatim (pass/fail counts).
6. `git diff --stat` one more time as a final atomic-change summary for the reviewer.

Do not run `git add`, `git commit`, `git merge`, `git push`, `git tag`, `gh release create`, or any deploy/cleanup step. Leave every change uncommitted and unstaged-or-staged exactly as your edits naturally leave them — the point is a clean, verified, reviewable diff sitting in the worktree.
</verification>

<success_criteria>
- `scripts/models.json` has exactly one new entry (`fable51`); the pre-existing `fable` entry's `command`/`claude_model_flag`/routing are byte-for-byte unchanged.
- No `fable5-1` entry exists anywhere.
- `python3 scripts/manage-models.py check` exits 0 (generated docs match registry).
- New focused tests pass; full `python3 -m pytest -q` passes with no failures or errors.
- Dry-run proves `--model fable` → `--model fable` in the generated command, and `--model fable51` → `--model claude-fable-5-1`.
- CHANGELOG.md has a new `[Unreleased]` entry citing both authoritative URLs.
- Nothing is committed, merged, pushed, tagged, released, or deployed. No file outside the dedicated executor worktree was touched. No API smoke call was made.
- Final report to the user includes: the verbatim `git diff --stat`, the verbatim final pytest summary line, and the two dry-run command outputs.
</success_criteria>

---
**Session Context**: For full conversation context, see: `/root/.claude/projects/-storage-projects-docker-worktrees-daplug-integration-fable51-20260903/349f1d48-74bd-4593-927b-1ad62075c652.jsonl`