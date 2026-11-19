<objective>
Add two daplug model shorthands, `deepseek` and `syn-ds41-flash`, that both route DeepSeek V4.1 Flash hosted on Synthetic through strict-direct OpenCode to the exact model `synthetic/hf:deepseek-ai/DeepSeek-V4.1-Flash`. Leave an atomic, verified, **uncommitted** implementation in this worktree for independent review — do not commit, merge, push, tag, release, bump the version, or delete the worktree.

This matters because daplug's model registry and router are hardcoded: a model that Synthetic already serves cannot be selected with `--model` until it has a registry entry, a router entry, and the generated docs/CLI choices that the single-source workflow derives from the registry. Today there is no DeepSeek shorthand at all. Both spellings are required: `syn-ds41-flash` follows the existing `syn-*` Synthetic naming, and `deepseek` is the short everyday alias the user will actually type.
</objective>

<authoritative_evidence>
Treat these facts as given. Do NOT make live API or network calls to re-verify them, and do not spend Synthetic quota on smoke runs. They were verified today (2026-09-15) against the live Synthetic `/openai/v1/models` response:

- Raw model ID: `hf:deepseek-ai/DeepSeek-V4.1-Flash` (provider `synthetic`)
- OpenCode provider ref: `synthetic/hf:deepseek-ai/DeepSeek-V4.1-Flash`; daplug internal colon form: `synthetic:hf:deepseek-ai/DeepSeek-V4.1-Flash`
- context_length 524288 (512k), max_output_length 65536 (64k)
- Input modalities: text + image (vision). Output: text
- Supports tools, json_mode, structured_outputs, reasoning
- Reasoning efforts accepted by the model: none, low, high, xhigh, max
- Requires `SYNTHETIC_API_KEY`, like every other `syn-*` shorthand

Baseline: this worktree is a clean branch from `origin/main` at `d48a03e` (v0.40.8). Installed plugin version is 0.40.8.
</authoritative_evidence>

<context>
Repo: daplug (Claude Code plugin). Work ONLY inside `/storage/projects/docker/worktrees/daplug-ds41-planning`. Do not touch the main checkout, other worktrees, `~/.config/opencode/opencode.json`, or anything Hermes-related (Hermes has its own custom Synthetic provider that live-discovers this model and needs no change).

The registry is the single source of truth (`scripts/models.json` says so in `model_order_note`). Inspect the CURRENT files before writing anything — do not copy structures from memory, from older prompts, or from this prompt's examples if the live files differ:

@scripts/models.json — read the full `syn-glm53-flash` entry (the most recent strict-direct Synthetic entry) and the `flash` / `glm53-flash` pair (the existing "canonical entry + `alias_of` alias" pattern). Note every field, the `command` list shape, the `routing` block shape, and the `docs` sub-fields.
@scripts/manage-models.py — read `REQUIRED_MODEL_FIELDS` / `REQUIRED_DOC_FIELDS` (top of file), the `alias_of` validation, and the `generate` / `check` subcommands. Read the CLAUDE.md "Generated Locations" table (14 numbered rows) to know every file `generate` rewrites.
@skills/cli-detector/scripts/router.py — read the `_SHORTHAND` block around the existing `syn-*` entries (each is a `_ModelRequest` with `family="synthetic"`, `force_cli="opencode"`, `strict_cli=True`) and the family-to-CLI map that lists `"synthetic": ["opencode"]`. Read `resolve_model` to understand how `strict_cli` overrides a cached/preferred CLI.
@skills/prompt-executor/scripts/models.py — read how `MODEL_SPECS` is derived from the registry, how `alias_of` is resolved, `SUPPORTED_VARIANTS`, and `_build_opencode_command` (which appends `--variant <v>` before `--pure --agent build`).
@skills/prompt-executor/scripts/executor.py — the `--model` argparse choices are derived from the registry; confirm no hand-maintained list needs editing.
@skills/cli-detector/scripts/plugins/opencode.py and @skills/cli-detector/scripts/fixer.py — read `_supported_providers`, `_required_env_for_provider`, and the opencode template/fix path. This is for the provider-registration validation in requirement 7; it is NOT a license to change the user's global OpenCode config.

Existing tests to use as templates (read them, then add sibling tests for the two new shorthands):
@scripts/tests/test_manage_models.py — `test_syn_glm53_flash_registry_entry`
@skills/cli-detector/tests/test_registry_consistency.py — `test_syn_glm53_flash_routes_to_synthetic_provider` and `test_syn_glm53_flash_resolves_strictly_to_opencode` (note the `_FakeCache` with codex installed, proving strict routing wins over a Codex cache preference)
@skills/cli-detector/tests/test_router.py — `SYNTHETIC_ROUTER_MODELS` and `test_synthetic_models_force_opencode_provider`
@skills/prompt-executor/tests/test_executor_variants.py — `SYNTHETIC_MODELS`, `test_synthetic_model_specs_are_opencode_provider_refs`, and the ordered shorthand list near the end of the file
@CHANGELOG.md — `[Unreleased]` section; match the prose/citation style of the `syn-glm53-flash` entry.

Do not read or modify anything under `prompts/completed/`.
</context>

<requirements>
1. **Preserve every existing alias and default.** `synthetic` stays `synthetic:syn:large:text`, `syn-flash` stays `synthetic:syn:small:text`, `syn-glm53-flash` stays `synthetic:hf:zai-org/GLM-5.3-Flash`, and `flash` / `glm53-flash` stay `zai:glm-5.3-flash`. No existing shorthand changes routing, model ID, variant default, or docs text. Reason: other prompts and user muscle memory depend on these; this change is purely additive.

2. **Add the canonical registry entry `syn-ds41-flash`** in `scripts/models.json`, placed immediately after `syn-glm53-flash` so the Synthetic block stays contiguous. Fill every field that `REQUIRED_MODEL_FIELDS` / `REQUIRED_DOC_FIELDS` require, mirroring the `syn-glm53-flash` shapes:
   - `model_id`: `synthetic:hf:deepseek-ai/DeepSeek-V4.1-Flash`
   - `default_cli`: `opencode`; `supports_codex_reasoning`: false; `codex_profile`, `claude_model_flag`, `alias_of`, `default_variant`: null; `env`: {}; `stdin_mode`: match the other `syn-*` entries
   - `command`: `["opencode","run","--format","json","-m","synthetic/hf:deepseek-ai/DeepSeek-V4.1-Flash","--pure","--agent","build"]`
   - `routing`: `{"cli_overrides":["opencode"],"force_direct_opencode":true,"google":false,"synthetic":true}` (confirm against the live `syn-glm53-flash` block; if the schema has gained or lost keys since, follow the live schema)
   - `docs`: family `Synthetic`, cli_label `opencode`, and descriptions that state: DeepSeek V4.1 Flash via Synthetic, 512k context, 64k max output, vision, tools/structured outputs, reasoning efforts none/low/high/xhigh/max. Keep `include_in_prompt_guides` consistent with `syn-glm53-flash`.

3. **Add the alias entry `deepseek`** immediately after `syn-ds41-flash`. Decide the mechanism by inspecting how `glm53-flash` aliases `flash`: if `alias_of` yields an identical command and identical router resolution, use `alias_of: "syn-ds41-flash"` with its own complete `docs` block (the generator requires docs on every entry, alias or not). If you find that `alias_of` does not produce identical executor and router behavior for strict Synthetic routing, make `deepseek` a full standalone entry instead and say why in your findings. Either way both shorthands must produce byte-identical commands.

4. **Router.** Add `_ModelRequest` entries for BOTH `syn-ds41-flash` and `deepseek` in `router.py`'s `_SHORTHAND`, each with `family="synthetic"`, `model_id="synthetic:hf:deepseek-ai/DeepSeek-V4.1-Flash"`, `force_cli="opencode"`, `strict_cli=True`, with a one-line comment like the `syn-glm53-flash` one. Do not add `deepseek` to any non-Synthetic family. Verify whether the router is itself derived from the registry (registry-consistency tests exist for a reason) and keep both in sync.

5. **Generated artifacts.** Run `python3 scripts/manage-models.py generate` and then `python3 scripts/manage-models.py check`. Accept only the diffs the generator produces in the 14 documented generated locations (SKILL.md option lists and tables, `commands/run-prompt.md`, `commands/prompts.md`, `commands/create-prompt.md`, `commands/create-llms-txt.md`, `README.md`, `CLAUDE.md`, and the executor's derived choices). Do not hand-edit inside generated regions. Do not create new docs or memory-bank files.

6. **CHANGELOG.** Add one `[Unreleased]` → `### Added` bullet for the two shorthands in the same style as the `syn-glm53-flash` bullet: both names, the OpenCode command, `SYNTHETIC_API_KEY` requirement, the model facts from `<authoritative_evidence>`, and a sentence stating that `synthetic`, `syn-flash`, and `syn-glm53-flash` defaults are unchanged.

7. **Provider registration validation (final response only, no global config edits).** Determine whether daplug's own model-management path (`manage-models.py`, the cli-detector `opencode` plugin, `fixer.py`, and any bridge/skill generators under `scripts/`) registers the `synthetic` provider and the `hf:deepseek-ai/DeepSeek-V4.1-Flash` model into OpenCode, or whether daplug relies on the user's pre-existing `~/.config/opencode/opencode.json` `provider.synthetic.models` block (as `syn-glm53-flash` appears to). Note that `_supported_providers` in the opencode plugin currently lists openai/anthropic/google/zai/local and no `synthetic`. Return the finding with file:line evidence in the executor's final response. If the repo has an established, tested mechanism that registers Synthetic models from the registry, wire the new model into it; if it does not, do NOT invent one here — state that the user must add the model to their own OpenCode config and stop there.

8. **Reasoning variants.** daplug's `SUPPORTED_VARIANTS` is `none/low/medium/high/xhigh`, while the model accepts `none/low/high/xhigh/max`. Do not widen or narrow `SUPPORTED_VARIANTS` in this prompt. Verify that `--variant low`, `--variant high`, and `--variant xhigh` pass through as `--variant <v>` in the OpenCode command for both shorthands. Note in your findings that `max` is currently unreachable through daplug and `medium` would be forwarded even though the model does not list it; leave both as-is.
</requirements>

<implementation>
- Insert, do not reorder: new registry entries go immediately after `syn-glm53-flash` so generated tables keep the Synthetic family contiguous and existing menu numbering only shifts after that point.
- Use the exact strings from `<authoritative_evidence>`. The colon form `synthetic:hf:deepseek-ai/DeepSeek-V4.1-Flash` is for `model_id` and router; the slash form `synthetic/hf:deepseek-ai/DeepSeek-V4.1-Flash` is for the OpenCode `-m` argument. Mixing them is the most likely bug in this change, so write the tests that would catch it.
- For maximum efficiency, when you need to read several independent files, read them in parallel rather than one at a time. After each generator or test run, reflect on the output before deciding the next step.
- No commits, merges, pushes, tags, releases, or version bumps. No `git stash`. No deleting or cleaning up unrelated files. No edits outside this worktree.
</implementation>

<output>
Modify in this worktree only:
- `./scripts/models.json` — two new entries (`syn-ds41-flash`, `deepseek`)
- `./skills/cli-detector/scripts/router.py` — two new `_SHORTHAND` entries
- `./CHANGELOG.md` — one `[Unreleased]` → `### Added` bullet
- Generated regions rewritten by `manage-models.py generate` (SKILL.md, commands/*.md, README.md, CLAUDE.md, executor derived choices) — generator output only
- Tests (see `<verification>`): additions to the four existing test files listed in `<context>`; no new test files unless the existing layout genuinely has no home for a case
</output>

<verification>
**Unit tests (REQUIRED).** Add sibling cases next to the `syn-glm53-flash` ones, covering BOTH `syn-ds41-flash` and `deepseek`:
- [ ] `scripts/tests/test_manage_models.py`: registry entries exist, `model_id`, `default_cli`, `command`, `routing`, `docs.family`, and the alias relationship (or standalone status) are exactly as specified; `default_command(...)` matches the stored command.
- [ ] `skills/cli-detector/tests/test_registry_consistency.py`: registry and `router._SHORTHAND` agree for both names; `resolve_model` returns `opencode` and the slash-form `-m` command for both even when the fake cache has Codex installed and a Codex CLI preference (mirror `test_syn_glm53_flash_resolves_strictly_to_opencode`, and add a case that passes an explicit Codex preference to prove strict routing wins).
- [ ] `skills/cli-detector/tests/test_router.py`: add both names to `SYNTHETIC_ROUTER_MODELS`.
- [ ] `skills/prompt-executor/tests/test_executor_variants.py`: add both to `SYNTHETIC_MODELS` and to the ordered shorthand list; add a case that `--variant high` and `--variant xhigh` produce `["opencode","run","--format","json","-m","synthetic/hf:deepseek-ai/DeepSeek-V4.1-Flash","--variant","<v>","--pure","--agent","build"]` for both shorthands.
- [ ] Existing assertions for `synthetic`, `syn-flash`, `syn-glm53-flash`, `flash`, `glm53-flash` still pass unchanged.

**Dry runs (no `--run`, no network).** Use a prompt that already exists (for example `009`) and confirm the printed command for each of the following contains `opencode run --format json -m synthetic/hf:deepseek-ai/DeepSeek-V4.1-Flash --pure --agent build`, with `--variant <v>` inserted before `--pure` when requested:
```bash
python3 skills/prompt-executor/scripts/executor.py 009 --model syn-ds41-flash
python3 skills/prompt-executor/scripts/executor.py 009 --model deepseek
python3 skills/prompt-executor/scripts/executor.py 009 --model syn-ds41-flash --variant high
python3 skills/prompt-executor/scripts/executor.py 009 --model deepseek --variant xhigh
python3 skills/prompt-executor/scripts/executor.py --help | grep -E "deepseek|syn-ds41-flash"
```
Also confirm `python3 skills/cli-detector/scripts/router.py --table` lists both shorthands under opencode.

**Focused suites, then the canonical full run:**
```bash
python3 -m pytest scripts/tests/test_manage_models.py -v
python3 -m pytest skills/cli-detector/tests/test_registry_consistency.py skills/cli-detector/tests/test_router.py -v
python3 -m pytest skills/prompt-executor/tests/test_executor_variants.py -v
python3 scripts/manage-models.py check
bash scripts/run-tests.sh
```
`scripts/run-tests.sh` is the single source of truth for CI and the release skill; it must exit 0. Include the relevant output from it and every dry-run command in the executor's final response.

Before declaring complete: `git status` shows only the files listed in `<output>`; `git diff --stat` shows no changes to `.claude-plugin/plugin.json`; no commits were created (`git log --oneline -1` is still `d48a03e`).
</verification>

<success_criteria>
- `--model deepseek` and `--model syn-ds41-flash` both resolve to strict-direct OpenCode with `-m synthetic/hf:deepseek-ai/DeepSeek-V4.1-Flash`, even with a Codex cache preference, and honor `--variant low/high/xhigh`.
- `manage-models.py check` is clean and all 14 generated locations reflect the new shorthands with no hand edits inside generated regions.
- All existing Synthetic, Z.AI, and other shorthands are byte-for-byte unchanged in the registry and router.
- Full `scripts/run-tests.sh` passes; the new tests fail if either shorthand is removed or the model string is altered.
- The executor's final response answers requirement 7 (provider registration path) and requirement 8 (variant coverage) with evidence, and the worktree holds an uncommitted, reviewable diff with no version bump, no commits, and no global OpenCode or Hermes config changes.
</success_criteria>

---
**Session Context**: For full conversation context, see: `/root/.claude/projects/-storage-projects-docker-worktrees-daplug-ds41-planning/8a40bbf1-5ac9-488d-9038-f2d37315d1f8.jsonl`