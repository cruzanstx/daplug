<objective>
Add support for newly available Gemini CLI models across daplug so users can select them consistently in execution, routing, docs, and prompt-generation menus.
This matters because model drift between Gemini CLI releases and daplug shorthands causes broken or missing model choices for users.
</objective>

<context>
Project: daplug Claude Code plugin with multi-CLI model routing.
Audience: maintainers and users invoking `/daplug:run-prompt` and related commands.
Read project conventions first in `./CLAUDE.md`.

Use authoritative upstream references before choosing model IDs:
- `https://github.com/google-gemini/gemini-cli/releases`
- Gemini CLI docs/changelog pages under `geminicli.com`

Current Gemini shorthands/patterns exist in:
- `./skills/prompt-executor/scripts/executor.py`
- `./skills/cli-detector/scripts/router.py`
- `./commands/gemini-cli.md`
- `./commands/run-prompt.md`
- `./commands/create-prompt.md`
- `./commands/create-llms-txt.md`
- `./skills/prompt-executor/SKILL.md`
- `./README.md`
- `./CLAUDE.md`
- `./skills/cli-detector/tests/test_router.py`
- `./skills/prompt-executor/scripts/test_executor_markers.py`
</context>

<research>
Thoroughly analyze current Gemini CLI model availability and pick only models that are actually valid and usable in headless CLI mode.
Consider multiple approaches for shorthand naming, then keep names consistent with existing conventions (e.g., `gemini25*`, `gemini3*`).
If any legacy shorthand points to deprecated IDs, update mappings and explain why in commit notes within the prompt output.
</research>

<requirements>
1. Follow the repository model-update checklist in `./CLAUDE.md` (Managing Models section).
2. Add/adjust Gemini model entries in executor model config and argparse model choices.
3. Update router shorthand -> provider model mapping for all added Gemini shorthands.
4. Update command docs and model menus so users see the new options everywhere they select models.
5. Keep naming, ordering, and wording aligned across all updated files.
6. Preserve backward compatibility for existing shorthands unless an upstream model is removed; if removed, provide a safe fallback mapping.
7. Ensure help text and tables do not list models that are not implemented in code.
</requirements>

<implementation>
Use this checklist exactly and keep it synchronized:
1. Update `models = {}` in `./skills/prompt-executor/scripts/executor.py`.
2. Update `--model` argparse choices in `./skills/prompt-executor/scripts/executor.py`.
3. Update model list + model reference table in `./skills/prompt-executor/SKILL.md`.
4. Update `--model` argument description in `./commands/run-prompt.md`.
5. Update preferred-agent/model options where applicable in `./commands/prompts.md`.
6. Update `<available_models>`, recommendation table, and model menus in `./commands/create-prompt.md`.
7. Update `<available_models>`, recommendation table, and model menu in `./commands/create-llms-txt.md`.
8. Update Gemini model tiers/shortcuts in `./README.md`.
9. Update model shorthand reference table in `./CLAUDE.md`.
10. Update/extend tests in `./skills/cli-detector/tests/test_router.py` and any executor tests impacted by new Gemini aliases.

Run helper checks:
- `python3 scripts/manage-models.py check`
- `python3 scripts/manage-models.py list`
</implementation>

<constraints>
- Do not invent model IDs; use upstream-confirmed names.
- Keep outputs ASCII and match existing style.
- Do not remove unrelated models.
- Keep changes scoped to model support and directly affected docs/tests.
- Explain WHY any model alias is added/changed when ambiguity exists, so future maintainers can audit decisions.
</constraints>

<validation>
Before declaring complete, verify all of the following:
1. `python3 skills/prompt-executor/scripts/executor.py --help` includes each new Gemini shorthand.
2. Command generation works for each new shorthand:
   - `python3 skills/prompt-executor/scripts/executor.py 001 --model <new-shorthand>`
3. Router tests pass:
   - `python3 -m pytest skills/cli-detector/tests/test_router.py -v`
4. Executor marker/model tests pass (or equivalent focused executor tests):
   - `python3 -m pytest skills/prompt-executor/scripts/test_executor_markers.py -v`
5. No mismatches remain between code-supported models and docs-listed models.
</validation>

<success_criteria>
- Newly added Gemini CLI models are fully available via daplug shorthands.
- All affected code, docs, and menus are consistent.
- Focused tests pass and model help output reflects the new options.
- Existing model behavior remains backward compatible.
</success_criteria>

<output>
Modify existing files in place (no new docs unless essential).
If a short implementation note is needed, save it to `./tmp/gemini-model-update-notes.md` and keep it concise.
</output>