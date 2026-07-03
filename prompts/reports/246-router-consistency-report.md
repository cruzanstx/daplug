# Router-Registry Consistency Check Report

## Design Decision

**Chosen: Design (b) -- consistency test with hardcoded `_SHORTHAND` retained.**

### Why not design (a) -- router loads from models.json at import time

Design (a) would make models.json the runtime source of truth for the router, eliminating duplication by construction. However, examining the actual fields revealed it is not clean for this codebase:

1. **Router-internal fields don't belong in the registry.** `_ModelRequest` has `force_cli`, `strict_cli`, `local_hint`, and `capabilities` -- these are routing implementation details, not model metadata. `force_cli="opencode"` with `strict_cli=True` is a routing policy ("this model must use opencode, no fallback"), not a property of the model itself. Adding these to models.json's `routing` sub-object would couple the registry to router internals, making models.json harder to maintain and reason about.

2. **Family values don't map 1:1.** models.json uses display names (`"Claude"`, `"OpenAI Codex"`, `"Z.AI / OpenCode"`) while the router uses internal identifiers (`"anthropic"`, `"openai"`, `"zai"`). Design (a) would either need to add a separate `router_family` field to every model (39 new fields) or embed a mapping table in the router -- which is itself a drift point.

3. **Invasiveness vs. risk.** Design (a) requires modifying 39 model entries in models.json, updating `manage-models.py` validation, and rewriting the router's import logic. Each of those carries risk of behavior change. Design (b) adds a single test file that touches nothing in the runtime path.

4. **The existing pattern already works.** `manage-models.py check` is a CI consistency gate for generated documentation. A consistency test for the router follows the same proven pattern -- drift is caught at CI time rather than prevented at import time, which is sufficient for a low-frequency change like model shorthand additions.

### What design (b) does

- Keeps `_SHORTHAND` hardcoded in `router.py` (zero runtime change).
- Adds `skills/cli-detector/tests/test_registry_consistency.py` with 10 tests that:
  - Assert shorthand key sets are identical (models.json vs. router).
  - Assert family fields agree (via an explicit mapping table).
  - Assert `reasoning_effort` agrees (derived from name suffix + `supports_codex_reasoning`).
  - Assert `model_id` agrees.
  - Simulate drift (missing key, extra key, family mismatch, reasoning_effort mismatch, model_id mismatch) and verify the error messages are actionable -- naming the specific shorthand and field.
- Uses stdlib only (`json`, `pathlib`, `dataclasses`).
- CI picks it up automatically: the existing workflow runs `pytest skills/cli-detector/tests/ -v`.

## Drift Audit

**No drift found.** All 39 models in `scripts/models.json` have matching entries in `router._SHORTHAND`, and every field checked is in agreement:

| Field | Check | Result |
|-------|-------|--------|
| Shorthand key set | 39 models.json models vs. 39 router entries | Identical |
| `model_id` | Per-model comparison | All 39 agree |
| Family | Mapped via display-name -> internal-name table | All 39 agree |
| `reasoning_effort` | Derived from name suffix (`-high`, `-xhigh`) gated by `supports_codex_reasoning` | All 39 agree |

### Family mapping used

| models.json `docs.family` | router `family` |
|---------------------------|-----------------|
| `"Claude"` | `"anthropic"` |
| `"OpenAI Codex"` | `"openai"` |
| `"Google Gemini"` | `"google"` |
| `"Z.AI / OpenCode"` | `"zai"` |
| `"Synthetic"` | `"synthetic"` |
| `"Local"` | `"local"` |

### Reasoning effort derivation logic

- If `supports_codex_reasoning` is `false` in models.json, expected `reasoning_effort` is `None` (regardless of name suffix). This covers all Gemini, Claude, ZAI, Synthetic, and Local models.
- If `supports_codex_reasoning` is `true` and the name ends with `-high`, expected `"high"`.
- If `supports_codex_reasoning` is `true` and the name ends with `-xhigh`, expected `"xhigh"`.
- Otherwise, expected `None`.

This correctly handles `gemini-high` and `gemini-xhigh`, which use different model IDs (e.g., `google:gemini-2.5-pro`) instead of the codex reasoning_effort flag.

## Zero Routing Behavior Change

No changes were made to `router.py`, `models.json`, or `manage-models.py`. The router's `_SHORTHAND` dict, `_ALIASES`, `_FALLBACK_CHAINS`, `_AGY_MODEL_ARGS`, `_build_command`, `resolve_model`, and all other routing logic are untouched. The 124 existing cli-detector tests pass unmodified. Spot-checking representative shorthands (`codex`, `codex-xhigh`, `gemini3pro`, `glm52`, `synthetic`, `qwen`, `devstral`, `cc-opus`) produces identical `(cli, model_id, cmd)` triples before and after the change.

## Verification

- All six pytest suites pass: `prompt-executor` (86), `cli-detector` (134 = 124 original + 10 new), `config-reader` (6), `sprint` (12), `at-prompt-runner` (50), `scripts/tests` (55). Total: 343.
- `python3 scripts/manage-models.py check` passes.
- `python3 scripts/manage-models.py generate` is a no-op ("already in sync").
- Router resolves representative shorthands identically.

## Files Changed

- **Added:** `skills/cli-detector/tests/test_registry_consistency.py` -- 10 tests, stdlib only.
- **Added:** `prompts/reports/246-router-consistency-report.md` -- this report.
- **Unchanged:** `router.py`, `models.json`, `manage-models.py` -- zero runtime impact.
