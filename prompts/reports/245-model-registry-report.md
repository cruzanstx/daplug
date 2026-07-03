# Model Registry Single Source Report

## Coverage Map

All 14 formerly manual checklist locations are now covered by `scripts/models.json` plus generated regions or runtime derivation:

| # | Location | Status |
|---|---|---|
| 1 | `skills/prompt-executor/scripts/executor.py` model definitions | Generated at runtime from `scripts/models.json` (`MODEL_SPECS`, command/env/stdin metadata, display map, aliases, routing sets). |
| 2 | `skills/prompt-executor/scripts/executor.py` `--model` choices | Generated at runtime from `MODEL_CHOICES`, derived from registry order. |
| 3 | `skills/prompt-executor/SKILL.md` `--model` options list | Generated: `skill-model-options`. |
| 4 | `skills/prompt-executor/SKILL.md` Model Reference table | Generated: `skill-model-reference`. |
| 5 | `commands/run-prompt.md` `--model` argument description | Generated: `run-prompt-model-argument`; frontmatter now uses generic `[--model <model>]` to avoid another model-list drift point. |
| 6 | `commands/prompts.md` preferred_agent options list | Generated: `preferred-agent-options`. |
| 7 | `commands/create-prompt.md` `<available_models>` section | Generated: `create-prompt-available-models`. |
| 8 | `commands/create-prompt.md` recommendation table | Generated: `create-prompt-recommendations`. |
| 9 | `commands/create-prompt.md` model selection menus | Generated in three regions: `create-prompt-selection-menu`, `create-prompt-parallel-selection-menu`, `create-prompt-sequential-selection-menu`. |
| 10 | `commands/create-llms-txt.md` `<available_models>` section | Generated: `create-llms-available-models`. |
| 11 | `commands/create-llms-txt.md` recommendation table | Generated: `create-llms-recommendations`. |
| 12 | `commands/create-llms-txt.md` model selection menu | Generated: `create-llms-selection-menu`. |
| 13 | `README.md` Model Tiers section | Generated: `readme-model-tiers`. |
| 14 | `CLAUDE.md` Model Shorthand Reference and checklist | Generated: `model-shorthand-table` and `generated-model-locations`; Managing Models prose now describes the registry workflow. |

No checklist location was excluded from `check`.

## Discrepancies Found

- `CLAUDE.md` previously combined `qwen`/`local` in one row while executor treated them as distinct shorthands. The generated table now has one row per registry model.
- `commands/create-prompt.md` and `commands/create-llms-txt.md` omitted `cc-sonnet`, `cc-opus`, `opencode`, `gemini-high`, `gemini-xhigh`, `gemini25lite`, `gemini3flash`, `glm-local`, and `qwen-small` from one or more menus. Generated menus now include every executor shorthand.
- Several prompt-command menus grouped `local/qwen/devstral` into one option. They are now separate entries because the registry treats them as separate executable shorthands.
- `commands/run-prompt.md` frontmatter had a full model list independent of the documented argument table. It now uses generic `[--model <model>]` so the generated table is the only model-list source in that file.
- The generated Managing Models verification example now uses active prompt `009`; prompt `001` is not active in this checkout, and `completed/001` is ambiguous between two archived prompts, so the old smoke command must be replaced with an active prompt or a full archived prompt path.

## router.py Overlap

`skills/cli-detector/scripts/router.py` still duplicates model metadata in `_SHORTHAND`: shorthand names, families, provider model IDs, reasoning effort aliases, `codex_profile`, local hints, and strict/default CLI routing. That overlaps substantially with `scripts/models.json`, but it was intentionally not refactored in this prompt per scope. Future work should either load shared registry metadata there or add a consistency check between router `_SHORTHAND` and `scripts/models.json` to prevent routing drift.

## Verification Notes

Passed:

- Full required pytest suites: prompt-executor, cli-detector, config-reader, sprint, at-prompt-runner, scripts (`333 passed`).
- `python3 scripts/manage-models.py check`.
- `python3 scripts/manage-models.py generate` is idempotent per `check`, unit tests, and generated-target checksum verification.
- `python3 skills/prompt-executor/scripts/executor.py --help` includes `synthetic`.
- Active prompt smoke tests passed with `009` for both `codex` and `glm52`.

Environment caveats:

- `git diff --exit-code` fails in this sandbox because the worktree `.git` metadata points at an unavailable common git dir: `/storage/projects/docker/daplug/.git/worktrees/daplug-prompt-245-20260702-215552`.
- The exact requested `executor.py 001 --model ...` smoke commands print `No prompt found for '001'` because no active `prompts/001-*.md` exists; `completed/001` is also ambiguous between two archived prompts.
