<objective>
Add Synthetic-hosted GLM-5.3-Flash to daplug as the first-class shorthand `syn-glm53-flash`, routing through OpenCode to `synthetic/hf:zai-org/GLM-5.3-Flash`.

This is distinct from the existing Z.AI Coding Plan shorthands `flash` and `glm53-flash`, which must remain unchanged and continue routing to `zai/glm-5.3-flash`.
</objective>

<context>
Repository: /storage/projects/docker/daplug. Read @CLAUDE.md first, especially “Managing Models” and generated-location rules.

Start from current `origin/main`, which already contains the released GLM-5.3-Flash Z.AI support in v0.40.5. The main checkout is dirty with unrelated Prompt 249 work. The executor worktree is the only allowed write location. Do not edit, stage, revert, clean, or include files from the main checkout.

Verified live Synthetic OpenAI-compatible `/models` response includes the exact model ID:
`hf:zai-org/GLM-5.3-Flash`

Required OpenCode provider reference:
`synthetic/hf:zai-org/GLM-5.3-Flash`

Expected internal daplug model ID:
`synthetic:hf:zai-org/GLM-5.3-Flash`

Expected generated command:
`opencode run --format json -m synthetic/hf:zai-org/GLM-5.3-Flash --pure --agent build`

Synthetic announcement facts supplied by the user:
- Beta release, first vision model in the GLM-5 family.
- Input price: $0.15/MTok; cached input: $0.04/MTok; output: $0.50/MTok.
- Synthetic reports it outperforming GLM-5.2 broadly and typically matching Opus 4.8.
Do not turn provider claims into independent benchmark conclusions.
</context>

<requirements>
1. Add `syn-glm53-flash` to @scripts/models.json, the single source of truth.
2. Follow the existing Synthetic model entries exactly:
   - `model_id`: `synthetic:hf:zai-org/GLM-5.3-Flash`
   - `default_cli`: `opencode`
   - `supports_codex_reasoning`: false
   - required environment: `SYNTHETIC_API_KEY`
   - routing family/provider: Synthetic
   - strict/direct OpenCode routing consistent with `syn-kimi3`, `syn-minimax`, and `syn-nemotron`
   - command exactly as shown above.
3. Document it as “GLM-5.3-Flash via Synthetic,” beta, vision-capable, and low-cost. Include the exact published prices only where concise model notes belong.
4. Do not change these existing routes or defaults:
   - `flash` / `glm53-flash` → Z.AI `zai/glm-5.3-flash`
   - `synthetic` → `synthetic/syn:large:text` (GLM-5.2)
   - `syn-flash` → `synthetic/syn:small:text`
   Keep GLM-5.2 as the generic Synthetic default while GLM-5.3-Flash is beta.
5. Add the router entry next to the other Synthetic entries in @skills/cli-detector/scripts/router.py with `family="synthetic"`, the exact internal model ID, `force_cli="opencode"`, and `strict_cli=True`.
6. Regenerate all managed regions using `python3 scripts/manage-models.py generate`. Never hand-edit generated regions.
7. Extend existing parametrized Synthetic tests rather than duplicating test structures:
   - @skills/prompt-executor/tests/test_executor_variants.py
   - @skills/cli-detector/tests/test_router.py
   - @skills/cli-detector/tests/test_registry_consistency.py
   - @scripts/tests/test_manage_models.py where applicable.
8. Update @CHANGELOG.md under `[Unreleased]` with the new shorthand, exact route, beta/vision status, and prices.
9. Update user-facing generated model references and any API-key error text generated or maintained by the registry so the new shorthand is listed.
10. Keep the diff atomic. Do not bump the version, commit, tag, publish, push, or install the plugin.
</requirements>

<verification>
Run and report actual output for every check:

```bash
python3 scripts/manage-models.py check
python3 -m pytest -q
python3 skills/prompt-executor/scripts/executor.py 001 --model syn-glm53-flash
python3 skills/cli-detector/scripts/router.py --table | grep -E 'syn-glm53-flash|glm53-flash|syn-flash'
python3 - <<'PY'
import sys
sys.path.insert(0, 'skills/cli-detector/scripts')
import router
for name in ('syn-glm53-flash', 'flash', 'glm53-flash', 'synthetic', 'syn-flash'):
    print(name, router.resolve_model(name))
PY
```

Real bounded Synthetic smoke test through daplug’s new route:

```bash
timeout 180 python3 skills/prompt-executor/scripts/executor.py \
  --prompt-file /tmp/daplug-glm53-flash-smoke.txt \
  --prompt-number smoke-glm53-flash \
  --model syn-glm53-flash --run
```

Create `/tmp/daplug-glm53-flash-smoke.txt` with exactly:
`Reply with exactly the text 42 and nothing else. Do not read or modify any files.`

Confirm:
- command resolves exactly to `synthetic/hf:zai-org/GLM-5.3-Flash`;
- smoke output contains assistant text `42` and exits 0;
- existing Z.AI `flash` / `glm53-flash` routes remain byte-for-byte unchanged;
- generic `synthetic` and `syn-flash` defaults remain unchanged;
- full test suite passes;
- no unrelated dirty-main files appear in the worktree diff.

Remove the temporary smoke prompt after verification.
</verification>

<success_criteria>
`daplug-run <prompt> --model syn-glm53-flash` resolves through OpenCode to Synthetic’s `hf:zai-org/GLM-5.3-Flash`, requires `SYNTHETIC_API_KEY`, is generated into all model references, is covered by registry/router/executor tests, and completes a real bounded smoke answer of `42`. Existing Z.AI and Synthetic aliases are unchanged. Leave a verified, uncommitted, atomic worktree diff for independent review.
</success_criteria>
