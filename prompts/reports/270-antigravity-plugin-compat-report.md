# Prompt 270: Antigravity plugin compatibility report

Date: 2026-11-17. Tools: agy 1.5.9, Claude Code `claude plugin validate`, daplug 0.40.19 (no version bump).

## Summary

| Requirement | Status |
|---|---|
| 1. Agent `tools:` as YAML lists | Done (10 files; `k8s-cicd-troubleshooter` has no `tools:` line) |
| 2. prompt-manager frontmatter | Done |
| 3. Bodies under 24000 bytes | Done; 0 truncation warnings |
| 4. Executor no-Google guard + tests | Done (`google_guard.py`, 33 tests) |
| 5. `assets/logo.svg` | Added; not referenced from Claude's plugin.json (see below) |
| 6. Docs | `docs/antigravity.md` + README "Antigravity (agy)" section |
| agy validate --strict: 0 errors | **Not met: 11 agent errors remain, needs an owner decision (below)** |
| Atomic commits | **Not made: git is unavailable in this sandbox (below)** |

## Blocker 1: agent `model:` tiers (owner decision needed)

The baseline's YAML `tools:` error hid a second error. Once `tools:` parses, agy rejects every agent with
`Invalid model tier sonnet|opus|haiku`. agy 1.5.9 accepts only `inherit`, `flash`, `pro` in agent frontmatter. I tested
`claude-sonnet-5-5`, `high`, `default`, `fast`, and `smart`, and all of them are rejected. The agy changelog embedded in the binary says
"Added a `model` option to custom agent frontmatter so an agent runs at a chosen model tier (such as `flash` or `pro`)
..., defaulting to `inherit`". Omitting `model:` also passes.

`inherit` is the only value both loaders accept. Using it would make agy load all 11 agents, but in Claude Code each
agent would run on the parent session's model instead of its pinned tier (`at-monitor` and `readonly-log-watcher` are `haiku`,
`at-fixer` is `opus`). That is a Claude cost and behavior change, and requirement 1 says to change nothing but the `tools:` lines. So I left
`model:` untouched. To accept the trade-off, run: `sed -i 's/^model: \(sonnet\|opus\|haiku\)$/model: inherit/' agents/*.md`.

### Iteration 2: workarounds tried that avoid changing Claude's tiers (each in a throwaway plugin + throwaway HOME)

| Approach | Result |
|---|---|
| Native `.antigravity-plugin/plugin.json` with `"agents": "./agy-agents"` | `unknown field "agents" is ignored`. The native manifest also turns off Claude conversion: commands are no longer converted and fail with `commands: never loaded`. Rejected. |
| Move Claude agents to `claude-agents/` and declare them in `.claude-plugin/plugin.json` `"agents": [...]` | Claude validates and loads them. agy ignores the field, so it loads **0 agents** with 0 errors. That only hides the problem, and the file moves break the "tools lines only" constraint. Rejected. |
| `.antigravityignore` listing `agents/x.md` (the string is in the agy binary) | Not applied by `plugin install`/`validate`; the agent still errors. |
| agy-native `agents/<name>/agent.md` with `model: pro` next to Claude's `agents/*.md` | agy loads it, but every agent prompt body would exist twice (one per loader), and the Claude `.md` files still error. Possible only with a generator and a sync check like `manage-models.py`. That is a larger design change for the owner. |

Conclusion: in agy 1.5.9, `inherit` (or omitting `model:`) is the only tier both loaders accept. Getting 0 agy errors therefore requires changing
the pinned Claude tiers, and the prompt forbids that. **Owner decision:** (a) switch to `model: inherit` (one `sed`, shown above), (b) build
generated agy-native agents, or (c) wait for agy to accept Claude tier names or ignore them.

## Blocker 2: no git in the sandbox

The worktree's `.git` file points at `/storage/projects/docker/daplug/.git/worktrees/...`, which this sandbox hides. Every `git`
command fails with `fatal: not a git repository`, so I could not make commits or run `git diff --stat` / `--color-moved`.
I checked the same properties another way (below). Suggested atomic commits:

1. `fix(agents): use YAML list for tools frontmatter`: `agents/*.md`
2. `fix(skills): add frontmatter to prompt-manager skill`: `skills/prompt-manager/SKILL.md`
3. `docs(agy): move long reference sections out of command and skill bodies`: `commands/{create-prompt,create-llms-txt,prompts,run-prompt}.md`, `skills/prompt-executor/SKILL.md`, `references/`, `skills/prompt-executor/references/`, `scripts/manage-models.py`, `CLAUDE.md` (regenerated location table), `scripts/tests/test_agy_compat.py`
4. `feat(executor): enforce no-Google policy for protected repos`: `skills/prompt-executor/scripts/{google_guard,executor}.py`, `skills/prompt-executor/tests/test_google_guard.py`
5. `docs(agy): add Antigravity install guide and logo`: `docs/antigravity.md`, `README.md`, `assets/logo.svg`, this report

## Verbatim and scope checks (instead of git diff)

Baseline = `cruzanstx/daplug@main` raw files. Their byte sizes match the measured 0.40.19 baseline exactly (50411, 33077, 26695, 26264, 26037).

- **Moved text.** A script put each reference body back in place of its pointer and compared the result with baseline.
  All five files came out `VERBATIM` (byte-identical).
- **Agents.** `diff` against baseline gives 20 changed lines across 10 files, all `tools:` lines (`grep -vc tools:` = 0).
- **prompt-manager.** The body after the new 5-line frontmatter is identical to baseline.
- **Generated regions.** `manage-models.py` now writes the moved regions in `references/`. Before I regenerated, `check` reported only the
  CLAUDE.md location-table change, so the moved regions regenerate byte-identical. `check` now passes.

## Size per trimmed file

The body is what agy measures: the bytes after the frontmatter.

| File | File bytes before | Body bytes before | File bytes after | Body bytes after |
|---|---:|---:|---:|---:|
| `commands/create-prompt.md` | 50411 | 50213 | 21897 | 21701 |
| `commands/create-llms-txt.md` | 33077 | 32927 | 22752 | 22604 |
| `commands/run-prompt.md` | 26695 | 26188 | 21411 | 20906 |
| `commands/prompts.md` | 26264 | 26073 | 21032 | 20843 |
| `skills/prompt-executor/SKILL.md` | 26037 | 25270 | 14592 | 13827 |

| Reference file | Moved from | Bytes |
|---|---|---:|
| `references/create-prompt-next-step-scenarios.md` | create-prompt `<single/parallel/sequential_scenario>` (3 generated menus) | 19008 |
| `references/create-prompt-available-models.md` | create-prompt `<available_models>` generated table | 8104 |
| `references/create-prompt-patterns.md` | create-prompt `## Prompt Patterns` | 3036 |
| `references/create-llms-txt-available-models.md` | create-llms-txt `<available_models>` generated table | 8104 |
| `references/create-llms-txt-examples.md` | create-llms-txt `## Example Interaction Flows` | 2082 |
| `references/create-llms-txt-special-case-templates.md` | create-llms-txt `### Special Case Templates` | 1446 |
| `references/prompts-preferred-agent-options.md` | prompts `preferred-agent-options` generated list | 5644 |
| `references/run-prompt-moa.md` | run-prompt `## Mixture of Agents (--moa)` | 3780 |
| `references/run-prompt-examples.md` | run-prompt `## Examples` | 2455 |
| `skills/prompt-executor/references/model-reference.md` | prompt-executor `## Model Reference` (generated table + notes) | 12013 |

Each main file keeps the operational core and a pointer (`$PLUGIN_ROOT/references/<file>`, or `references/model-reference.md` beside
the skill). `test_agy_compat.py` checks that every pointer resolves and that every reference file has a pointer.

Command references live in the top-level `references/` directory, not `commands/references/`. `claude plugin validate` showed that Claude
treats `commands/references/*.md` as extra commands, which would have broken "21 commands". The tightest margin is
`create-llms-txt.md` at 22604 body bytes, about 1.4 KB of headroom; its generated selection menu grows about 120 B per new model. The test
will fail CI before agy starts truncating.

## agy validate: before

```
Validating daplug ($H/.gemini/config/plugins/daplug/plugin.json)

  ✗ agents/at-fixer.md: the frontmatter isn't valid YAML: failed to unmarshal frontmatter YAML: yaml: unmarshal errors:
  line 4: cannot unmarshal !!str `Read, G...` into []string. The loader skips this agent
  ✗ agents/at-merger.md: the frontmatter isn't valid YAML: failed to unmarshal frontmatter YAML: yaml: unmarshal errors:
  line 4: cannot unmarshal !!str `Read, G...` into []string. The loader skips this agent
  ✗ agents/at-monitor.md: the frontmatter isn't valid YAML: failed to unmarshal frontmatter YAML: yaml: unmarshal errors:
  line 4: cannot unmarshal !!str `Bash, R...` into []string. The loader skips this agent
  ✗ agents/at-planner.md: the frontmatter isn't valid YAML: failed to unmarshal frontmatter YAML: yaml: unmarshal errors:
  line 4: cannot unmarshal !!str `Read, G...` into []string. The loader skips this agent
  ✗ agents/at-validator.md: the frontmatter isn't valid YAML: failed to unmarshal frontmatter YAML: yaml: unmarshal errors:
  line 4: cannot unmarshal !!str `Read, G...` into []string. The loader skips this agent
  ✗ agents/frontend-build-optimizer.md: the frontmatter isn't valid YAML: failed to unmarshal frontmatter YAML: yaml: unmarshal errors:
  line 3: cannot unmarshal !!str `Read, E...` into []string. The loader skips this agent
  ✗ agents/go-build-optimizer.md: the frontmatter isn't valid YAML: failed to unmarshal frontmatter YAML: yaml: unmarshal errors:
  line 3: cannot unmarshal !!str `Read, E...` into []string. The loader skips this agent
  ✗ agents/infra-troubleshooter.md: the frontmatter isn't valid YAML: failed to unmarshal frontmatter YAML: yaml: unmarshal errors:
  line 40: cannot unmarshal !!str `Read, E...` into []string. The loader skips this agent
  ✗ agents/k8s-cicd-troubleshooter.md: model output error: invalid tool call error (invalid_args) Invalid model tier sonnet. The loader skips this agent
  ✗ agents/pipeline-deploy-monitor.md: the frontmatter isn't valid YAML: failed to unmarshal frontmatter YAML: yaml: unmarshal errors:
  line 33: cannot unmarshal !!str `Bash, R...` into []string. The loader skips this agent
  ✗ agents/readonly-log-watcher.md: the frontmatter isn't valid YAML: failed to unmarshal frontmatter YAML: yaml: unmarshal errors:
  line 3: cannot unmarshal !!str `Read, Grep` into []string. The loader skips this agent
  ✗ skills/prompt-manager/SKILL.md: no frontmatter: the file must start with a --- block holding name and description. The loader skips this skill
  ⚠ skills/daplug-cmd-create-llms-txt/SKILL.md: the body is 32927 bytes; only the first 24000 are loaded
  ⚠ skills/daplug-cmd-create-prompt/SKILL.md: the body is 50213 bytes; only the first 24000 are loaded
  ⚠ skills/daplug-cmd-prompts/SKILL.md: the body is 26073 bytes; only the first 24000 are loaded
  ⚠ skills/daplug-cmd-run-prompt/SKILL.md: the body is 26188 bytes; only the first 24000 are loaded
  ⚠ skills/prompt-executor/SKILL.md: the body is 25270 bytes; only the first 24000 are loaded
  · plugin.json: no logo: the plugin shows a generic icon. Add "logo": "assets/logo.svg" (a .png, .svg, .jpg, .jpeg or .webp file inside the plugin)

  skills 32 · agents 0 · rules 0 · hooks 1 · mcpServers 0 · sidecars 0

Error: validation failed: 12 errors, 5 warnings
```

## agy install + validate --strict: after

```
  [ok]    daplug
          ✔ skills      : 12 installed (ai-usage, at-prompt-creator, at-prompt-runner, cli-detector, config-reader, handoff, prompt-executor, prompt-finder, prompt-manager, sprint, tmux-manager, worktree)
          ✔ agents      : 11 installed (at-fixer, at-merger, at-monitor, at-planner, at-validator, frontend-build-optimizer, go-build-optimizer, infra-troubleshooter, k8s-cicd-troubleshooter, pipeline-deploy-monitor, readonly-log-watcher)
          ✔ commands    : 21 installed (converted to skills) (cclimits, check-config, check-updates, codex-cli, create-at-prompt, create-llms-txt, create-prompt, detect-clis, devstral-cli, gemini-cli, handoff, install-bridges, migrate-config, prompts, qwen-cli, resume-handoff, run-at-prompt, run-prompt, sprint, uvc, zai-cli)
          ✔ hooks       : 1 installed (PostToolUse)
          Installed to $H/.gemini/config/plugins/daplug
Validating daplug ($H/.gemini/config/plugins/daplug/plugin.json)

  ✗ agents/at-fixer.md: model output error: invalid tool call error (invalid_args) Invalid model tier opus. The loader skips this agent
  ✗ agents/at-merger.md: model output error: invalid tool call error (invalid_args) Invalid model tier sonnet. The loader skips this agent
  ✗ agents/at-monitor.md: model output error: invalid tool call error (invalid_args) Invalid model tier haiku. The loader skips this agent
  ✗ agents/at-planner.md: model output error: invalid tool call error (invalid_args) Invalid model tier sonnet. The loader skips this agent
  ✗ agents/at-validator.md: model output error: invalid tool call error (invalid_args) Invalid model tier sonnet. The loader skips this agent
  ✗ agents/frontend-build-optimizer.md: model output error: invalid tool call error (invalid_args) Invalid model tier sonnet. The loader skips this agent
  ✗ agents/go-build-optimizer.md: model output error: invalid tool call error (invalid_args) Invalid model tier sonnet. The loader skips this agent
  ✗ agents/infra-troubleshooter.md: model output error: invalid tool call error (invalid_args) Invalid model tier sonnet. The loader skips this agent
  ✗ agents/k8s-cicd-troubleshooter.md: model output error: invalid tool call error (invalid_args) Invalid model tier sonnet. The loader skips this agent
  ✗ agents/pipeline-deploy-monitor.md: model output error: invalid tool call error (invalid_args) Invalid model tier sonnet. The loader skips this agent
  ✗ agents/readonly-log-watcher.md: model output error: invalid tool call error (invalid_args) Invalid model tier haiku. The loader skips this agent
  · plugin.json: no logo: the plugin shows a generic icon. Add "logo": "assets/logo.svg" (a .png, .svg, .jpg, .jpeg or .webp file inside the plugin)

  skills 33 · agents 0 · rules 0 · hooks 1 · mcpServers 0 · sidecars 0

Error: validation failed: 11 errors, 0 warnings
```

Results:
- 0 warnings and no truncation.
- skills went from 32 to 33 (prompt-manager now loads).
- The only errors left are the 11 agent model tiers (Blocker 1).
- `no logo` is an info note. agy's converter writes its own `plugin.json` and drops a `logo` field even when Claude's manifest has one
  (tested). Claude's validator reports `logo` as an unknown field. So I added `assets/logo.svg` and left both manifests without the reference.

## Claude side

`claude plugin validate .claude-plugin/plugin.json` passes with warnings. The warnings are the same as baseline: a root `CLAUDE.md` note,
an unquoted `${CLAUDE_PLUGIN_ROOT}` in the hook, and a missing PNG icon. There are no new errors or warnings, and the agents parse with list `tools:`.
Inventory: 21 `commands/*.md` (no nested `.md`), 12 `skills/*/SKILL.md`, 11 `agents/*.md`, and `hooks/hooks.json` unchanged.

## Executor no-Google guard

Module: `skills/prompt-executor/scripts/google_guard.py`, a separate module that keeps the prompt-248 split. It is imported by `executor.py`.

- **Env, default, and override.** `DAPLUG_NO_GOOGLE_REPOS` defaults to `tldrhq|youtube[_-]?summaries`. When unset, the default applies.
  `''` (or only whitespace) disables the guard.
- **Match targets.** The repo root, `--cwd`, `--original-repo-root`, and `--worktree-path`, plus each one's `origin` URL.
- **Google route.** `routing.google == true`, or `default_cli` in {agy, gemini}, or `--cli agy|antigravity|gemini`. Every `--moa`
  entry is checked, including `model:cli` overrides. Unknown models are refused, like the wrapper does.
- **Ordering.**
  - The first check runs right after argument and repo-root resolution: before `get_cli_info` (so no agy preflight), prompt
    resolution, worktree creation, and `cli-logs` mkdir.
  - A second check runs after CLI resolution and refuses if preferred-agent routing lands on agy/gemini.
  - Both checks apply in preview mode (no `--run`). `--loop-status` stays allowed because it is read-only.
- **Refusal.** stderr gets the wrapper-style message, stdout gets JSON `{"error": ..., "refused": "no_google_policy"}`, and the exit code is 2
  (the wrapper's code).

Deliberate differences from `~/.local/bin/daplug-run`:
1. **Case-insensitive match.** The wrapper's bash `=~` is case-sensitive, so a `TLDRHQ` directory was not protected. The executor
   fails closed.
2. **Empty override.** The wrapper uses `${DAPLUG_NO_GOOGLE_REPOS:-default}`, which treats `''` as unset, so the documented bypass
   `DAPLUG_NO_GOOGLE_REPOS=''` does not actually disable the wrapper guard. The executor follows the specified semantics. The wrapper is outside
   this repo and unchanged; changing `:-` to `-` there would align it.
3. **Invalid regex.** An invalid `DAPLUG_NO_GOOGLE_REPOS` regex fails closed, but only for Google routes.

### Guard tests (`skills/prompt-executor/tests/test_google_guard.py`, 33 passing)

- `test_blocked_on_repo_path_match`
- `test_blocked_on_repo_path_match_case_insensitive`
- `test_blocked_on_origin_url_match`
- `test_blocked_on_cli_agy_with_non_google_model`
- `test_blocked_on_other_google_cli_spellings[gemini]`
- `test_blocked_on_other_google_cli_spellings[antigravity]`
- `test_blocked_on_model_with_default_cli_agy`
- `test_blocked_on_model_with_routing_google`
- `test_blocked_in_preview_mode`
- `test_blocked_before_worktree_creation`
- `test_blocked_when_any_moa_entry_is_google`
- `test_blocked_when_cwd_points_into_protected_repo`
- `test_blocked_when_router_resolves_to_google_cli`
- `test_invalid_regex_fails_closed`
- `test_allowed_google_route_in_non_matching_repo`
- `test_allowed_non_google_route_in_protected_repo`
- `test_allowed_when_override_is_empty`
- `test_custom_pattern_replaces_default`
- `test_google_route_reason[agy-only-None-agy`
- `test_google_route_reason[google-flag-None-routing.google=true]`
- `test_google_route_reason[gemini-cli-None-gemini`
- `test_google_route_reason[plain-agy---cli`
- `test_google_route_reason[plain-Antigravity---cli`
- `test_google_route_reason[missing-None-not`
- `test_google_route_reason[plain-None-None]`
- `test_google_route_reason[plain-opencode-None]`
- `test_pattern_defaults_and_override`
- `test_default_pattern_matches_protected_names[tldrhq]`
- `test_default_pattern_matches_protected_names[youtubesummaries]`
- `test_default_pattern_matches_protected_names[youtube-summaries]`
- `test_default_pattern_matches_protected_names[youtube_summaries]`
- `test_default_pattern_matches_protected_names[my-TLDRHQ-fork]`
- `test_direct_executor_invocation_refuses`

## Test results

- `scripts/run-tests.sh` passes:
  - prompt-executor: 433 passed, 3 skipped
  - cli-detector: 217 passed, 1 skipped
  - config-reader: 6
  - handoff: 14
  - sprint: 12
  - at-prompt-runner: 50
  - scripts: 120
  - the model registry check
- A root `python3 -m pytest -q` run gives 902 passed and 4 skipped. The baseline run before changes gave 809 passed and 4 skipped.
- New tests: 33 guard tests and 60 agy-compat tests.

## Iteration 3 (final) re-check, 2026-11-17

No code changes. Re-ran everything: full pytest gives 902 passed and 4 skipped. `manage-models.py check` is in sync.
`claude plugin validate .` passes, with warnings. A fresh throwaway-HOME agy install + `validate --strict` gives 0 truncation warnings and
0 skill errors. The only errors left are the 11 `Invalid model tier` agent errors from Blocker 1. Git is still unavailable (Blocker 2).
Both blockers need the owner: pick option (a), (b) or (c) for agent tiers, and make the 5 suggested commits from a checkout with git access.
