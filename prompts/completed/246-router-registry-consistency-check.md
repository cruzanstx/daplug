<objective>
Prevent routing drift between the model registry and the CLI router. Prompt 245 made `scripts/models.json` the single source of truth for daplug's model shorthands, but `skills/cli-detector/scripts/router.py` still hardcodes its own `_SHORTHAND` dict (shorthand names, families, provider model IDs, reasoning efforts, capabilities, CLI routing hints, codex profiles). A model added to models.json today will silently be missing from router-based routing, and vice versa. Add an automated consistency check between the two so drift fails CI, and share data where it is cheap to do so.
</objective>

<context>
This is the daplug Claude Code plugin repo. Read CLAUDE.md ("Managing Models" section) and prompts/reports/245-model-registry-report.md first — the report's "router.py Overlap" section is the origin of this task.

Key files:
@scripts/models.json — the registry (single source of truth since prompt 245)
@skills/cli-detector/scripts/router.py — `_ModelRequest` dataclass (~line 25) and `_SHORTHAND` dict (~line 39); routing logic below
@skills/cli-detector/tests/test_router.py — existing router tests, including TestAllModelsHaveValidCommands
@scripts/manage-models.py — the generate/check tooling; check is the CI entry point
@.github/workflows/tests.yml — CI already runs the cli-detector suite and manage-models.py check

Design constraint: router.py must remain importable and functional standalone within the cli-detector skill (it is imported by detect_clis and the executor's routing path). Keep changes conservative — the router's routing BEHAVIOR must not change for any existing shorthand.
</context>

<requirements>
1. **Decide and implement the sync mechanism.** Two acceptable designs — pick one after examining the code, and justify the choice in your final report:
   a. (Preferred if clean) Router loads shorthand metadata from scripts/models.json at import time, keeping `_ModelRequest` as the in-memory shape. Resolve the models.json path relative to the router script's own location (../../../scripts/models.json from skills/cli-detector/scripts/), NOT the CWD, with a clear error if missing. Models.json may need a small additive `routing` sub-object per model to carry router-only fields (family, reasoning_effort, capabilities, force_cli, strict_cli, local_hint, codex_profile) — additive changes to models.json schema are fine, but manage-models.py generate/check must keep passing.
   b. (Fallback if (a) is too invasive) Keep `_SHORTHAND` hardcoded but add a consistency test that fails when the shorthand key set OR the per-model routing-relevant fields disagree with models.json. The test must produce an actionable diff message naming the drifted shorthands and fields.

2. **Either way, add a consistency test** in skills/cli-detector/tests/ asserting: every models.json model has a router entry, every router entry has a models.json model, and reasoning-effort/family fields agree. This is the CI tripwire.

3. **Zero behavior change**: the existing cli-detector test suite (124 tests) must pass unmodified, except tests whose assertions are about the data source itself. Do not add third-party dependencies — stdlib only.

4. **Update prompts/reports/245-model-registry-report.md** is NOT needed; instead write your own report (see output).
</requirements>

<verification>
All must pass before declaring completion:

```bash
for suite in skills/prompt-executor/tests skills/cli-detector/tests skills/config-reader/tests skills/sprint/tests skills/at-prompt-runner/tests scripts/tests; do
  python3 -m pytest "$suite" -q || exit 1
done
python3 scripts/manage-models.py check
python3 scripts/manage-models.py generate && git status --short  # generate stays a no-op

# Router still resolves representative shorthands identically (spot-check output before/after your change):
python3 -c "
import sys; sys.path.insert(0, 'skills/cli-detector/scripts')
import router
for s in ['codex', 'codex-xhigh', 'gemini3pro', 'glm52', 'synthetic', 'qwen', 'devstral', 'cc-opus']:
    print(s, router._SHORTHAND[s] if hasattr(router, '_SHORTHAND') else router.resolve(s))
"
```

New tests required:
- [ ] shorthand key sets of router and models.json are identical (the tripwire)
- [ ] per-shorthand agreement on family and reasoning_effort
- [ ] drift produces an actionable failure message (simulate by patching a copy of the data in the test)
- [ ] if design (a): router import fails with a clear error when models.json is missing/malformed, and loads correctly when CWD is not the repo root
</verification>

<output>
- Modified: `./skills/cli-detector/scripts/router.py` and/or new consistency test in `./skills/cli-detector/tests/`
- Possibly modified (design a): `./scripts/models.json`, `./scripts/manage-models.py`
- Report: `./prompts/reports/246-router-consistency-report.md` — which design you chose and why, any drift found between the current router and models.json (list every disagreement), and confirmation of zero routing behavior change
</output>

<success_criteria>
- A model added to models.json without router coverage (or vice versa) fails the test suite with a message naming the model
- All six pytest suites pass; manage-models.py check passes; generate remains a no-op
- Identical routing decisions for every existing shorthand
</success_criteria>