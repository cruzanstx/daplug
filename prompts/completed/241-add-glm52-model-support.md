<objective>
Add GLM-5.2 support to daplug by introducing a new `glm52` shorthand and retargeting the existing `glm5` shorthand to point at GLM-5.2. This makes the latest GLM 5.x model available under both names while leaving all other shorthands (`zai`, `opencode`, `glm-local`, etc.) unchanged.

The Z.AI Coding Plan API now supports GLM-5.2 with a 1M context window. This prompt covers every file in the Managing Models checklist plus cli-detector routing, tests, docs, and templates.
</objective>

<context>
Repo: /storage/projects/docker/daplug (main, v0.27.2)

Current GLM state (from CLAUDE.md model table before this change):
- `zai`       → GLM-4.7 via Z.AI (do NOT change)
- `glm5`      → GLM-5 via OpenCode (retarget to GLM-5.2)
- `opencode`  → GLM-4.7 via OpenCode (do NOT change)
- `glm-local` → glm-4.7-flash via LMStudio (do NOT change)

GLM-5.2 technical specs (from official Z.AI Coding Plan docs):
- API endpoint:    https://api.z.ai/api/coding/paas/v4  (NOT the general paas/v4)
- Raw model id:    glm-5.2
- OpenCode ref:    zai/glm-5.2
- Context window:  1,000,000 tokens
- Max output:      131,072 tokens
- Image support:   disabled (not documented for Coding Plan)
- Claude Code env: ANTHROPIC_DEFAULT_SONNET_MODEL=glm-5.2[1m]
                   ANTHROPIC_DEFAULT_OPUS_MODEL=glm-5.2[1m]
                   CLAUDE_CODE_AUTO_COMPACT_WINDOW=1000000

CAUTION: A prior WIP worktree (`.worktrees/daplug-prompt-238-20260327-202837`) targeted GLM-5.1
and broadened scope excessively. Do NOT use it as reference. It is stale and wrong.

Read CLAUDE.md before starting — especially the "Managing Models" section (lines 193–229) which
lists every file that must be updated when adding a model.
</context>

<scope_boundaries>
MUST change:
- `glm5` shorthand  → retarget from GLM-5 to GLM-5.2 (keep the name)
- `glm52` shorthand → add as new explicit GLM-5.2 alias

MUST NOT change (unless changing is strictly required by repo internals — see justification rule):
- `zai` shorthand
- `opencode` shorthand
- `glm-local` shorthand
- Any OpenAI gpt-* shorthand
- Any Gemini shorthand
- Kimi shorthand
- Any LMStudio local shorthands (qwen, devstral, qwen-small)

JUSTIFICATION RULE: If you find that changing `zai` or `opencode` is unavoidable due to
repo conventions, document your reasoning explicitly in a comment near the change AND include
a summary in your final output under a `<scope_justification>` section. Do not change them
silently.
</scope_boundaries>

<requirements>
Implement the following changes across all relevant files:

## 1. executor.py — LEGACY_MODEL_DISPLAY, MODEL_SPECS, and argparse choices

File: `skills/prompt-executor/scripts/executor.py`

There is no `models = {}` command dict. The two structures to update are:

**a) `LEGACY_MODEL_DISPLAY` (around line 665)** — add `"glm52"` and update `"glm5"`:

```python
"glm5": "glm5 (GLM-5.2 via OpenCode — latest GLM 5.x, 1M context)",
"glm52": "glm52 (GLM-5.2 via OpenCode — explicit pin, 1M context)",
```

**b) `MODEL_SPECS` (around line 808)** — update `"glm5"` `model_id` and add `"glm52"`:

```python
"glm5": {
    "model_id": "zai:glm-5.2",
    "default_cli": "opencode",
    "supports_codex_reasoning": False,
    "codex_profile": "glm5",
    "claude_model_flag": None,
},
"glm52": {
    "model_id": "zai:glm-5.2",
    "default_cli": "opencode",
    "supports_codex_reasoning": False,
    "codex_profile": None,
    "claude_model_flag": None,
},
```

The internal `model_id` uses the `zai:` prefix (`zai:glm-5.2`). The executor's
`_build_opencode_command` converts this via `_opencode_model_spec` to `zai/glm-5.2`, so the
generated command will be: `opencode run --format json -m zai/glm-5.2`

**c) argparse choices** — add `"glm52"` to all choice lists that already contain `"glm5"`
(search for `"glm5"` in argparse sections to find every occurrence).

> Note on context window: daplug passes the model ID only; it does not set context-window
> flags. The 1M window is active automatically when using the Coding Plan endpoint with
> `glm-5.2`. Do NOT invent new executor flags for context-window size.

## 2. cli-detector router

File: `skills/cli-detector/scripts/router.py`

The existing `glm5` entry (around line 112) uses `_ModelRequest`:

```python
"glm5": _ModelRequest("glm5", family="zai", model_id="zai:glm-5", codex_profile="glm5"),
```

Update `glm5` to `zai:glm-5.2` and add `glm52` beside it:

```python
"glm5": _ModelRequest("glm5", family="zai", model_id="zai:glm-5.2", codex_profile="glm5"),
"glm52": _ModelRequest("glm52", family="zai", model_id="zai:glm-5.2"),
```

Also check `skills/cli-detector/scripts/` and `skills/cli-detector/tests/` for any related
templates, plugin files, or test fixtures that list model shorthands and update them too.

## 3. prompt-executor SKILL.md

File: `skills/prompt-executor/SKILL.md`

- Add `glm52` to the `--model` options list with description "GLM-5.2 via Z.AI / OpenCode (1M context)"
- Update `glm5` description to reflect GLM-5.2 target
- Add/update the Model Reference table row for both shorthands

## 4. commands/run-prompt.md

File: `commands/run-prompt.md`

Add `glm52` to the `--model` argument description and update `glm5` entry.

## 5. commands/prompts.md

File: `commands/prompts.md`

Update the preferred_agent options list to reflect `glm52` and updated `glm5`.

## 6. commands/create-prompt.md

File: `commands/create-prompt.md`

Three locations to update:
- `<available_models>` section
- Recommendation logic table
- Model selection menus (all 3 instances)

Add `glm52` and update `glm5` in all three.

## 7. commands/create-llms-txt.md

File: `commands/create-llms-txt.md`

- `<available_models>` section
- Recommendation logic table
- Model selection menu

## 8. README.md

File: `README.md`

Update the Model Tiers / model reference section to add `glm52` and update `glm5`.

## 9. CLAUDE.md

File: `CLAUDE.md`

Update the "Model Shorthand Reference" table:
- Change `glm5` row: GLM-5 → GLM-5.2 via OpenCode
- Add `glm52` row: GLM-5.2 via OpenCode (explicit pin)

Include a note about the 1M context window and the `glm-5.2[1m]` form used in Claude Code
env vars versus the `zai/glm-5.2` form used in OpenCode.

## 10. scripts/manage-models.py (if it maintains a model registry)

File: `scripts/manage-models.py`

If this script reads from a registry or has a hardcoded model list, add `glm52` and update
`glm5` there as well. Run `python3 scripts/manage-models.py check` to confirm consistency.
</requirements>

<implementation_notes>
- Internal model_id representation: `zai:glm-5.2` (colon-separated provider prefix)
- Generated OpenCode CLI command: `opencode run --format json -m zai/glm-5.2`
  (the `-m` flag, NOT `--model`; `_build_opencode_command` constructs this via
  `_opencode_model_spec` which converts `zai:glm-5.2` → `zai/glm-5.2`)
- Raw model ID for Z.AI API / docs / env var examples: `glm-5.2`
- Claude Code env var form: `glm-5.2[1m]` (the `[1m]` suffix activates 1M context window);
  this form appears only in documentation/comments, NOT in executor data structures
- daplug does not set context-window flags; the 1M window is automatic via the Coding Plan endpoint
- Do NOT change `~/.config/opencode/opencode.json` (user-level config); that is out of scope
- Check whether `skills/cli-detector/` has plugin templates or JSON fixtures that enumerate
  models — update those if found
</implementation_notes>

<verification>
Run each command and confirm expected output. Do not skip any step.

```bash
# 1. Full test suite
python3 -m pytest -q

# 2. Model management consistency check
python3 scripts/manage-models.py check

# 3. Help text shows both shorthands
python3 skills/prompt-executor/scripts/executor.py --help | grep -E "glm5|glm52|zai|opencode"

# 4. Dry-run glm52 — should print the opencode command with zai/glm-5.2
python3 skills/prompt-executor/scripts/executor.py 021 --model glm52

# 5. Dry-run glm5 — should also print opencode command with zai/glm-5.2
python3 skills/prompt-executor/scripts/executor.py 021 --model glm5

# 6. Router table shows glm5/glm52 routing to zai/glm-5.2 via opencode
PYTHONPATH=skills/cli-detector/scripts python3 skills/cli-detector/scripts/router.py --table | grep -E "glm5|glm52|zai|opencode"
```

If any verification command fails, fix the issue before declaring done.
</verification>

<success_criteria>
The implementation is complete when ALL of the following are true:

1. `glm52` is a valid `--model` value in executor.py, SKILL.md, run-prompt.md, and all menus
2. Both `glm52` and `glm5` resolve to model `zai/glm-5.2` (GLM-5.2) in executor output
3. The `glm5` shorthand name is preserved (not renamed or removed)
4. `zai` and `opencode` shorthands remain pointing at GLM-4.7 — OR a `<scope_justification>`
   section in your final output explains exactly why they had to change
5. No OpenAI, Gemini, Kimi, or LMStudio shorthands are modified
6. All 10 file categories in `<requirements>` are updated
7. `python3 -m pytest -q` passes with no new failures
8. `python3 scripts/manage-models.py check` reports consistency
9. CLAUDE.md model table reflects both `glm52` and updated `glm5` rows
10. GLM-5.2 long-context information (1M window, `glm-5.2[1m]` env var form, coding plan
    endpoint) is documented in at least CLAUDE.md and SKILL.md
</success_criteria>

<constraints>
- SCOPE: Only touch files directly relevant to adding `glm52` and updating `glm5`
- DO NOT commit, merge, push, create tags, or create GitHub releases
- DO NOT delete worktrees or clean unrelated files
- DO NOT modify any other shorthands unless explicitly required (and justified per the
  JUSTIFICATION RULE in `<scope_boundaries>`)
- DO NOT change `~/.config/opencode/opencode.json` or any user-level config outside the repo
- The 1M context window is automatic via the Coding Plan endpoint; do not invent new
  executor flags for it
- Read CLAUDE.md "Managing Models" section before starting to ensure no file is missed
</constraints>