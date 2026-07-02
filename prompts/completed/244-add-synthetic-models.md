<objective>
Wire Synthetic (https://synthetic.new) into daplug as a first-class model provider so users can run prompts against Synthetic-hosted models via `/daplug:run-prompt --model synthetic` (and a small set of explicit shorthands), with full documentation and quota-style usage parity with existing providers.

Synthetic offers a subscription-priced, OpenAI- and Anthropic-compatible API that fronts GLM-5.2, Kimi-K2.6, Qwen3.6-27B, MiniMax-M3, Nemotron, and other open-weights models. Adding it gives users another fallback when Codex / Gemini / Z.AI quotas are exhausted.
</objective>

<context>
Repository: daplug (Claude Code plugin), Python executor lives at `skills/prompt-executor/scripts/executor.py`.

**Synthetic facts (verified 2026-06-27 from https://dev.synthetic.new/docs/):**
- Auth: `Authorization: Bearer $SYNTHETIC_API_KEY`. Users get keys from https://synthetic.new dashboard.
- OpenAI-compatible base URL: `https://api.synthetic.new/openai/v1` (endpoints: `/chat/completions`, `/completions`, `/embeddings`, `/models`).
- Anthropic-compatible base URL: `https://api.synthetic.new/anthropic` (endpoints: `/messages`, `/messages/count_tokens`).
- Quotas endpoint: `GET https://api.synthetic.new/v2/quotas` → `{"subscription":{"limit": N, "requests": N, "renewsAt": "<ISO8601>"}}`. Calls to `/v2/quotas` do **not** count against the quota.
- Pricing model is request-count subscription (not per-token).

**Always-on models (use `syn:` aliases — they auto-resolve to current best `hf:` ID):**
| Alias | Resolves to | Context | Modality |
|---|---|---|---|
| `syn:large:text` | `hf:zai-org/GLM-5.2` | 512k (beta) | Text |
| `syn:small:text` | `hf:zai-org/GLM-4.7-Flash` | 192k | Text |
| `syn:large:vision` | `hf:moonshotai/Kimi-K2.6` | 256k | Vision |
| `syn:small:vision` | `hf:Qwen/Qwen3.6-27B` | 256k | Vision |

Other always-on raw IDs available if needed: `hf:MiniMaxAI/MiniMax-M3`, `hf:nvidia/NVIDIA-Nemotron-3-Super-120B-A12B-NVFP4`, `hf:openai/gpt-oss-120b`, `hf:zai-org/GLM-4.7`, `hf:zai-org/GLM-5.1`, `hf:Qwen/Qwen3.5-397B-A17B`. Embeddings: `hf:nomic-ai/nomic-embed-text-v1.5`.

**Documented Claude Code env-var drop-in (from /docs/guides/claude-code):**
```
ANTHROPIC_BASE_URL=https://api.synthetic.new/anthropic
ANTHROPIC_AUTH_TOKEN=$SYNTHETIC_API_KEY
ANTHROPIC_DEFAULT_OPUS_MODEL=syn:large:vision
ANTHROPIC_DEFAULT_SONNET_MODEL=syn:large:vision
ANTHROPIC_DEFAULT_HAIKU_MODEL=syn:small:text
CLAUDE_CODE_SUBAGENT_MODEL=syn:large:vision
CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1
CLAUDE_CODE_ATTRIBUTION_HEADER=0
```

**Existing daplug patterns to follow (read these before coding):**
- `@skills/prompt-executor/scripts/executor.py` — `MODEL_SPECS` (line ~797), `MODEL_ALIAS_BASE` (~737), `MODEL_ALIAS_DEFAULT_VARIANT` (~748), `LEGACY_MODEL_DISPLAY` (~759). Look at how `glm5` / `glm52` / `kimi` / `opencode` are wired — they all go through OpenCode with `default_cli: "opencode"` and a `model_id` like `zai:glm-5.2` or `opencode:kimi-k2.5`.
- `@skills/cli-detector/scripts/providers.py` and `@skills/cli-detector/scripts/router.py` — provider registration and routing tables.
- `@scripts/manage-models.py` — checklist tool that walks every file needing a model entry. Run `python3 scripts/manage-models.py check` before and after changes to verify coverage.
- `@CLAUDE.md` — the 14-file checklist under "Managing Models" is authoritative.
</context>

<requirements>
1. **Choose the integration path.** Two reasonable approaches — pick one and justify briefly in the PR description (you do not need to implement both):
   - **(A) OpenCode provider** (preferred, matches `glm5`/`kimi` pattern): add a `synthetic` provider entry that OpenCode can route to via the OpenAI-compatible base URL. Requires the user's `~/.config/opencode/opencode.json` to know about Synthetic; document the snippet.
   - **(B) Codex CLI profile** (matches `zai`): add a codex profile with `OPENAI_BASE_URL=https://api.synthetic.new/openai/v1` and `OPENAI_API_KEY=$SYNTHETIC_API_KEY`.

2. **Add these shorthands to executor.py (`MODEL_SPECS` + `LEGACY_MODEL_DISPLAY` + argparse `--model` choices):**
   - `synthetic` — default Synthetic alias → `syn:large:text` (GLM-5.2, 512k context). Display: "synthetic (GLM-5.2 via Synthetic, 512k context)".
   - `syn-flash` — `syn:small:text` (GLM-4.7-Flash). Display: "syn-flash (GLM-4.7-Flash via Synthetic)".
   - `syn-kimi` — `syn:large:vision` (Kimi-K2.6). Display: "syn-kimi (Kimi-K2.6 via Synthetic, vision)".
   - `syn-qwen` — `syn:small:vision` (Qwen3.6-27B). Display: "syn-qwen (Qwen3.6-27B via Synthetic, vision)".
   
   Do **not** add the raw `hf:` IDs as shorthands — keep the surface small. Document them as available-via-pass-through in SKILL.md.

3. **Env var contract:** the executor must error with a clear message if `SYNTHETIC_API_KEY` is unset when a `syn-*` / `synthetic` shorthand is requested. Follow the same pattern Z.AI uses for `ZAI_API_KEY` etc.

4. **Quota awareness hook:** add a `cclimits`-style probe (or note for the user) that calls `GET https://api.synthetic.new/v2/quotas` and reports `requests / limit (renews at renewsAt)`. If `cclimits` is wired into `/daplug:ai-usage` (see `skills/ai-usage/` if present, otherwise wherever quota detection lives), extend it with a `synthetic` provider. If that surface area is larger than one file, scope this to a follow-up TODO comment and a docs note — do **not** balloon the change.

5. **Documentation updates — the 14-file checklist in CLAUDE.md.** Use `python3 scripts/manage-models.py check` to verify nothing is missed. At minimum:
   - `skills/prompt-executor/scripts/executor.py` (MODEL_SPECS + argparse choices + LEGACY_MODEL_DISPLAY)
   - `skills/prompt-executor/SKILL.md` (`--model` options + Model Reference table)
   - `commands/run-prompt.md`, `commands/prompts.md`, `commands/create-prompt.md` (3 menu instances + recommendation table), `commands/create-llms-txt.md`
   - `README.md` Model Tiers section
   - `CLAUDE.md` Model Shorthand Reference table

6. **Tests.** Add to `skills/prompt-executor/tests/` (or wherever model-shorthand tests live):
   - `synthetic`, `syn-flash`, `syn-kimi`, `syn-qwen` resolve to the correct provider + model_id.
   - argparse `--model` accepts all four shorthands.
   - Missing `SYNTHETIC_API_KEY` produces the expected error (skip the actual network call).

7. **No behavior change for existing models.** Verify `manage-models.py list` output before/after — only adds, no edits or removes.
</requirements>

<implementation>
Thoroughly analyze existing patterns before coding. Read the comparable provider wiring (`glm5`/`glm52`/`kimi` and `zai`) end-to-end so the new entries feel native, not bolted on.

Step-by-step:
1. Read `@CLAUDE.md` "Managing Models" section + run `python3 scripts/manage-models.py check`. Capture the baseline.
2. Read `@skills/prompt-executor/scripts/executor.py` around `MODEL_SPECS` and `LEGACY_MODEL_DISPLAY`. Pick approach (A) or (B) from requirement #1.
3. Read `@skills/cli-detector/scripts/providers.py` to see how providers get registered. Add a `synthetic` provider if approach (A); otherwise add a codex profile entry under `~/.codex/config.toml` documentation if (B).
4. Add the four `MODEL_SPECS` entries with `default_cli` set per approach choice. Mirror the shape of existing entries — same fields, same casing.
5. Extend the argparse `--model` choices to include `synthetic`, `syn-flash`, `syn-kimi`, `syn-qwen`.
6. Add a `SYNTHETIC_API_KEY` presence check on dispatch path (mirror Z.AI's check).
7. Update documentation files in the 14-file checklist. Use the existing entries for `glm5`/`kimi` as templates — copy structure, swap values.
8. Add tests. Run `cd skills/prompt-executor && python3 -m pytest tests/ -v` and `cd skills/config-reader && python3 -m pytest tests/ -v`.
9. Run `python3 scripts/manage-models.py check` again and confirm zero missing references.
10. Sanity check: `python3 skills/prompt-executor/scripts/executor.py --help | grep -E 'synthetic|syn-'` shows all four.

Constraints (and **why** they matter):
- **Do not invent new CLI infrastructure.** Synthetic should ride on top of OpenCode or codex, exactly like `glm5`/`zai`. Adding a bespoke `synthetic` CLI integration is out of scope and would create maintenance burden when OpenCode/codex already speak OpenAI-compatible APIs.
- **Keep shorthand count small (4).** Each shorthand multiplies docs maintenance across 14 files. Raw `hf:` IDs stay available via pass-through but don't get their own row.
- **No secrets committed.** `SYNTHETIC_API_KEY` must come from the user's shell env. Provide a `.env.example`-style snippet in docs, not a real key.
- **Don't break `manage-models.py`.** It introspects executor.py at import time — keep `MODEL_SPECS` syntactically valid and field-complete.
</implementation>

<output>
Modify these files (paths relative to repo root):
- `./skills/prompt-executor/scripts/executor.py` — add 4 entries to `MODEL_SPECS`, `LEGACY_MODEL_DISPLAY`, argparse choices, and the API-key presence check.
- `./skills/cli-detector/scripts/providers.py` (and/or `router.py`) — register `synthetic` if approach (A); otherwise add codex profile bookkeeping.
- `./skills/prompt-executor/SKILL.md` — Model Reference table + `--model` options list.
- `./commands/run-prompt.md`, `./commands/prompts.md`, `./commands/create-prompt.md`, `./commands/create-llms-txt.md` — model menus, recommendation tables, `<available_models>` blocks.
- `./README.md` — Model Tiers section.
- `./CLAUDE.md` — Model Shorthand Reference table + a short "Synthetic" subsection noting env var, base URLs, and quotas endpoint.
- `./skills/prompt-executor/tests/` (or appropriate test module) — new test cases per requirement #6.

Do **not** create new files unless absolutely necessary (e.g. a single new test file if no existing one fits). Do not commit any `.env` or key material.
</output>

<verification>
**Unit Tests** (REQUIRED):
```bash
cd skills/prompt-executor && python3 -m pytest tests/ -v
cd skills/config-reader && python3 -m pytest tests/ -v
```

Tests must cover:
- [ ] `synthetic`, `syn-flash`, `syn-kimi`, `syn-qwen` resolve to correct `model_id` + `default_cli` in `MODEL_SPECS`.
- [ ] argparse `--model` accepts each of the four shorthands.
- [ ] Missing `SYNTHETIC_API_KEY` raises the expected error (mock `os.environ`; no network).
- [ ] `manage-models.py check` reports zero missing references for the new shorthands.

Manual smoke checks (no actual model call required):
```bash
# 1. New shorthands appear in argparse help
python3 skills/prompt-executor/scripts/executor.py --help | grep -E 'synthetic|syn-flash|syn-kimi|syn-qwen'

# 2. manage-models.py finds them everywhere
python3 scripts/manage-models.py list | grep -E 'synthetic|syn-'
python3 scripts/manage-models.py check  # should report 0 missing

# 3. Dry-run dispatch with API key set (will print resolved command, no network)
SYNTHETIC_API_KEY=dummy python3 skills/prompt-executor/scripts/executor.py 001 --model synthetic
SYNTHETIC_API_KEY=dummy python3 skills/prompt-executor/scripts/executor.py 001 --model syn-kimi

# 4. Missing-key error is clear
unset SYNTHETIC_API_KEY && python3 skills/prompt-executor/scripts/executor.py 001 --model synthetic
# Expect: clear error message naming SYNTHETIC_API_KEY
```

Before declaring complete:
- [ ] `python3 scripts/manage-models.py check` exits clean.
- [ ] All four shorthands documented in CLAUDE.md table, README, SKILL.md, and all command menus.
- [ ] Existing models (`glm5`, `kimi`, `codex`, etc.) still resolve identically — verify with a diff of `manage-models.py list` before/after.
- [ ] No `.env` files staged; `git diff --cached` clean of secrets.
</verification>

<success_criteria>
1. `python3 skills/prompt-executor/scripts/executor.py --model synthetic <prompt>` dispatches to OpenCode (or codex per approach choice) with Synthetic base URL + `SYNTHETIC_API_KEY` and resolves `syn:large:text` server-side.
2. `synthetic`, `syn-flash`, `syn-kimi`, `syn-qwen` are listed in argparse help, SKILL.md, run-prompt.md, prompts.md, create-prompt.md, create-llms-txt.md, README.md, and CLAUDE.md.
3. All unit tests pass; `manage-models.py check` reports zero misses.
4. CLAUDE.md has a short "Synthetic" doc block documenting: env var name, OpenAI/Anthropic base URLs, quotas endpoint, and a one-line opencode.json (or `~/.codex/config.toml`) example.
5. No regressions in existing model dispatch (verified by diffing `manage-models.py list` and existing pytest suites green).
</success_criteria>