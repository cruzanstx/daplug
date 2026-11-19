<objective>
Bump the default Gemini shorthands in daplug from Gemini 3.7 Flash to Gemini 3.8 Flash.

`agy models` on this host now lists `gemini-3.8-flash-high/medium/low` with Antigravity display names
`Gemini 3.8 Flash (High)`, `Gemini 3.8 Flash (Medium)`, `Gemini 3.8 Flash (Low)` (agy 1.1.25). The bare
`gemini`, `agy`, and `gemini37*` shorthands are the project's "latest Flash" aliases, so they must move to
3.8 in the registry, the three hand-maintained runtime display maps, the generated docs, the CLI fixture,
and every test that pins the 3.7 strings. Users who run `/daplug:run-prompt --model gemini` should get
3.8 Flash after this change.
</objective>

<context>
daplug is a Claude Code plugin. Read `./CLAUDE.md` first, especially "Managing Models" and the
generated-region map. Model definitions live in `scripts/models.json`; `scripts/manage-models.py generate`
rewrites the markdown regions bounded by `<!-- BEGIN GENERATED: ... -->` markers.

Three Python files carry a HAND-MAINTAINED copy of the agy display-name map (NOT generated). A
consistency test asserts all three are byte-identical to each other, so they must be edited together:
- `skills/cli-detector/scripts/router.py` (`_SHORTHAND` model_ids, `_AGY_MODEL_ARGS`)
- `skills/cli-detector/scripts/plugins/agy.py` (`_AGY_MODEL_ARGS`, `_AGY_DEFAULT_MODEL_ARG`, and the `get_available_models` entries with `id="google:gemini-3.7-flash"` / `display_name="Gemini 3.7 Flash (...)"`)
- `skills/prompt-executor/scripts/models.py` (`_AGY_MODEL_ARGS`)

`scripts/manage-models.py` has its own `AGY_DISPLAY_NAMES` map (line ~182) and `AGY_DEFAULT_DISPLAY_NAME`
(line ~191) used when rendering commands into docs.

The test suite also compares router display names against a captured fixture of `agy models` output:
`skills/cli-detector/tests/fixtures/agy-models.txt`. That fixture must be recaptured live so the 3.8 names exist in it.

Find every occurrence before starting:
```bash
grep -rn "3\.7 Flash\|gemini-3\.7-flash" --include="*.py" --include="*.json" --include="*.md" --include="*.txt" . | grep -v "^./prompts/"
```
</context>

<requirements>
1. `scripts/models.json`: for entries `gemini`, `agy`, `gemini37`, `gemini37-high`, `gemini37-medium`, `gemini37-low` change
   `model_id` `google:gemini-3.7-flash` -> `google:gemini-3.8-flash`, and every command/docs display string
   `Gemini 3.7 Flash (High|Medium|Low)` -> `Gemini 3.8 Flash (High|Medium|Low)`. Update descriptions that say "3.7 Flash"
   as the current default. Keep the `gemini37*` shorthand NAMES unchanged (they are retained aliases; only their target moves).
   Legacy `gemini` CLI fallback commands for these entries must become `gemini -y -m gemini-3.8-flash -p`.
2. `scripts/manage-models.py`: `AGY_DISPLAY_NAMES` key `google:gemini-3.7-flash` -> `google:gemini-3.8-flash` with value
   `Gemini 3.8 Flash (High)`; `AGY_DEFAULT_DISPLAY_NAME = "Gemini 3.8 Flash (High)"`.
3. `skills/cli-detector/scripts/router.py`: `_SHORTHAND` entries for `gemini`, `agy`, `gemini37`, `gemini37-high`,
   `gemini37-medium`, `gemini37-low` -> `model_id="google:gemini-3.8-flash"`; `_AGY_MODEL_ARGS` keys/values to the 3.8
   equivalents (key `google:gemini-3.8-flash`, values byte-exact `Gemini 3.8 Flash (High)` / `(Medium)` / `(Low)`); update the
   two comments that say 3.7.
4. `skills/cli-detector/scripts/plugins/agy.py` and `skills/prompt-executor/scripts/models.py`: apply the identical
   `_AGY_MODEL_ARGS` edit so all three maps stay equal. In `agy.py` also update `_AGY_DEFAULT_MODEL_ARG` and the
   `get_available_models` model entries (id + display_name).
5. Run `python3 scripts/manage-models.py generate`. This refreshes `CLAUDE.md`, `README.md`, `commands/create-prompt.md`,
   `commands/create-llms-txt.md`, `commands/prompts.md`, `commands/run-prompt.md`, and `skills/prompt-executor/SKILL.md`.
   Then hand-edit any remaining prose in those files (outside generated regions) that documents 3.7 Flash as the current default.
6. `commands/gemini-cli.md`: the `gemini` row in the model table (`-m gemini-3.7-flash` -> `-m gemini-3.8-flash`, description
   "Gemini 3.8 Flash (default; same model as the `agy` shorthand)") and the `*)` default case arm
   (`MODEL_FLAG="-m gemini-3.8-flash"`, comment "gemini default (3.8 Flash)").
7. `CHANGELOG.md`: add an Unreleased entry "Gemini default shorthands (`gemini`, `agy`, `gemini37*`) now target Gemini 3.8 Flash".
   Do not rewrite historical entries that describe the earlier 3.7 bump.
8. `skills/cli-detector/tests/fixtures/agy-models.txt`: recapture live. Run `agy models 2>/dev/null` and
   `agy --version`, replace the block between `# --- BEGIN agy models ---` and `# --- END agy models ---` with the raw
   tab-separated output (exclude the progress line), and update the `Captured live:` date to 2026-09-03 and the version line.
9. Update tests that pin the 3.7 strings to the 3.8 equivalents (model_id `google:gemini-3.8-flash`, display names
   `Gemini 3.8 Flash (...)`, legacy command `["gemini", "-y", "-m", "gemini-3.8-flash", "-p"]`):
   - `skills/cli-detector/tests/test_router.py`
   - `skills/cli-detector/tests/test_registry_consistency.py` (the `expected` map, the `{"google:gemini-3.7-flash"}` model_id set, the agy command tuple, and the three fixture display-name asserts)
   - `skills/cli-detector/tests/test_plugins.py`
   - `skills/prompt-executor/tests/test_executor_variants.py`
   - `skills/prompt-executor/tests/test_agy_execution.py`
   - `skills/prompt-executor/tests/test_agy_stream.py`
   - `skills/prompt-executor/tests/test_sandbox.py` (including the fake `agy models` probe stdout)
   - `scripts/tests/test_manage_models.py` (only if it asserts a 3.7 string; grep found none, confirm)
   Rename test functions/docstrings that say "gemini37 ... 3.7 Flash" only where the wording becomes false; the
   `gemini37` shorthand name itself stays.
</requirements>

<constraints>
- Preserve `gemini-3.7-flash` / "3.7 Flash" text ONLY where it documents retained backwards-compat behaviour or
  history (CHANGELOG history, `gemini3flash` legacy notes, comments explaining that `gemini37*` are kept as aliases).
  Everything that describes the CURRENT default must say 3.8.
- Do NOT touch `zai`, `codex`, `claude`, `synthetic`, `local`, or other non-Google entries in `models.json`.
- Do NOT change executor control flow, `sandbox.py`, `build_bwrap_args`, worktree code, or preflight logic. Only the
  string maps/tests listed above change. Reason: this is a data bump; behaviour changes would mask regressions in
  the consistency tests that guard the three-way map equality.
- Do NOT edit inside generated regions by hand; change `scripts/models.json` and regenerate. Hand edits there are
  overwritten by the next `generate` and fail `check`.
- Do not bump `.claude-plugin/plugin.json` version; release is a separate step.
</constraints>

<verification>
Run from the repo root and require ALL of the following:

```bash
python3 scripts/manage-models.py generate
python3 scripts/manage-models.py check          # exit 0, "in sync"
python3 -m pytest -q                            # all green, zero failures/errors
```

Router probes (each must print model_id `google:gemini-3.8-flash` and the byte-exact display arg):
```bash
R=skills/cli-detector/scripts/router.py
for s in gemini agy gemini37 gemini37-high gemini37-medium gemini37-low; do
  python3 "$R" --resolve "$s" --json
done
python3 -c "
import sys; sys.path.insert(0,'skills/cli-detector/scripts')
import router
for s in ['gemini','agy','gemini37','gemini37-high','gemini37-medium','gemini37-low']:
    r = router._SHORTHAND[s]; print(s, r.model_id, repr(router._AGY_MODEL_ARGS[s]))
"
```
Expected display args: High/High/High/High/Medium/Low, all prefixed `Gemini 3.8 Flash `.

Legacy gemini CLI fallback (must yield `-m gemini-3.8-flash`):
```bash
python3 skills/prompt-executor/scripts/executor.py 001 --model gemini --cli gemini
python3 skills/prompt-executor/scripts/executor.py 001 --model gemini37-low --cli gemini
```

Final sweep, the only remaining hits must be legacy/history wording:
```bash
grep -rn "3\.7 Flash\|gemini-3\.7-flash" --include="*.py" --include="*.json" --include="*.md" --include="*.txt" . | grep -v "^./prompts/"
```

Confirm all three `_AGY_MODEL_ARGS` maps are identical:
```bash
diff <(grep -A9 "_AGY_MODEL_ARGS = {" skills/cli-detector/scripts/router.py) <(grep -A9 "_AGY_MODEL_ARGS = {" skills/cli-detector/scripts/plugins/agy.py)
```
</verification>

<success_criteria>
- `python3 -m pytest -q` passes with no failures.
- `python3 scripts/manage-models.py check` exits 0.
- `gemini`, `agy`, `gemini37`, `gemini37-high`, `gemini37-medium`, `gemini37-low` resolve to `google:gemini-3.8-flash`
  with agy args `Gemini 3.8 Flash (High|Medium|Low)` and legacy fallback `gemini -y -m gemini-3.8-flash -p`.
- The agy-models fixture contains the live 3.8 display names and the capture header is dated 2026-09-03.
- No diff outside the Google/Gemini entries, the three display maps, generated docs, gemini-cli.md, CHANGELOG.md,
  the fixture, and the listed tests.
</success_criteria>

---
**Session Context**: For full conversation context, see: `/root/.claude/projects/-storage-projects-docker-worktrees-daplug-integration-fable51-20260903/9c9c8c94-c6dc-4e6e-92dc-6b7de7d91968.jsonl`