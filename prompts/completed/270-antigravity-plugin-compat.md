<objective>
Make the daplug repo install and load cleanly as an Antigravity (agy 1.5.9+) plugin via `agy plugin install <repo>`, while staying a fully working Claude Code plugin. Also enforce the TLDRHQ/youtubesummaries no-Google policy inside the executor itself, because an agy-driven daplug run would not pass through `~/.local/bin/daplug-run`.

Claude Code behavior must not regress. Every change must be accepted or ignored by Claude Code's plugin loader.
</objective>

<context>
Read CLAUDE.md for repo conventions.

Measured baseline (agy 1.5.9, daplug 0.40.19, installed into a throwaway HOME):
`HOME=$TMPDIR/x agy plugin install <repo>` converts the plugin. Commands become `daplug-cmd-<name>` skills, the `Bash` hook matcher becomes `run_command`, and it writes `plugin.json` + `hooks.json`. `agy plugin validate <converted dir>` then reports 12 errors and 5 warnings:

1. All 11 `agents/*.md` are skipped. Frontmatter `tools: Read, Grep, Bash` is a string, and agy requires a YAML list. Claude Code accepts both.
2. `skills/prompt-manager/SKILL.md` is skipped because it has no `---` frontmatter (name + description).
3. Bodies over 24000 bytes are truncated: commands/create-prompt.md (50 KB), commands/create-llms-txt.md (33 KB), commands/run-prompt.md (27 KB), commands/prompts.md (26 KB), skills/prompt-executor/SKILL.md (26 KB).
4. Info only: no logo.

Path note: skills hardcode `~/.claude/plugins`, `~/.claude/cli-logs`, `~/.claude/loop-state`, and resolve helpers via `~/.claude/plugins/installed_plugins.json`. That is intentionally left as is. Shared state across Claude, Hermes and agy is desired. Do NOT relocate state dirs.

No-Google guard: `~/.local/bin/daplug-run` (outside this repo, lines ~66-90) refuses Google routes when the repo dir or origin URL matches `DAPLUG_NO_GOOGLE_REPOS` (default `tldrhq|youtube[_-]?summaries`). Google routes are any model whose registry entry has `routing.google == true` OR `default_cli` in {agy, gemini}, plus `--cli agy|gemini`. This lives only in the wrapper, so direct `executor.py` invocations bypass it.
</context>

<requirements>
1. Agents: convert every `tools:` frontmatter value in `agents/*.md` to a YAML list. Change nothing else in those files.
2. prompt-manager: add valid frontmatter (`name: prompt-manager`, a one-line trigger-style `description`). Body unchanged.
3. Size: get every SKILL.md and command body under 24000 bytes. Move long reference sections verbatim into `references/*.md` beside the skill (or `commands/references/` for commands), and leave a short pointer plus the operational core in the main file. Never delete instructions. A moved section must be reachable from a pointer in the main file.
4. Executor guard: port the wrapper's no-Google check into the executor (prompt-executor scripts; respect the module split from prompt 248), with the same env var, default regex, override semantics (`DAPLUG_NO_GOOGLE_REPOS=''` disables it), match on repo root path AND `origin` URL, and the same Google-route definition. Refuse with a clear message and non-zero exit BEFORE creating any worktree or log. Add unit tests: blocked (path match, origin match, `--cli agy`, model with default_cli agy, model with routing.google), allowed (non-matching repo, override empty), and preview mode also blocked.
5. Add `assets/logo.svg` (simple, square, transparent background). Reference it only if Claude's plugin.json schema tolerates the field. Otherwise skip the reference, because agy reads it from its own generated plugin.json.
6. Add a `docs/antigravity.md` section or README section: install command, what converts, known limits (hook only fires on run_command, state shared under ~/.claude).
</requirements>

<verification>
- Full pytest suite passes. The new guard tests pass.
- Claude side: `claude plugin validate .` (or the repo's existing manifest check) passes.
- agy side, in a throwaway HOME only:
  `H=$(mktemp -d); HOME=$H agy plugin install "$PWD" && HOME=$H agy plugin validate "$H/.gemini/config/plugins/daplug" --strict`
  Result: 0 errors, and no truncation warnings. Paste the output in the report. Remove $H afterward.
- `git diff --stat` shows agents changes limited to the tools lines, and moved reference text verbatim (diff-check with `git diff --color-moved`).
</verification>

<output>
- Changes above, atomic commits per requirement, scoped messages (`fix(agents): ...`, `feat(executor): ...`, `docs(agy): ...`).
- Report: `prompts/reports/270-antigravity-plugin-compat-report.md` with before/after validate output, byte sizes per trimmed file, and the guard test list.
- No version bump or release. The owner publishes separately.
</output>

<success_criteria>
- agy validate --strict: 0 errors and 0 warnings, apart from optional info notes.
- Claude Code still loads all 21 commands, 12 skills, 11 agents and the hook.
- Direct executor invocation refuses Google routes for TLDRHQ/youtubesummaries repos.
</success_criteria>
