# Using daplug with Antigravity (agy)

daplug is a Claude Code plugin first. Antigravity CLI (`agy` 1.5.9+) can install it directly from the repo and convert it on the fly. This page covers what converts, what does not, and the known limits.

## Install

```bash
# From a local checkout
agy plugin install /path/to/daplug

# Or from the GitHub repo
agy plugin install https://github.com/cruzanstx/daplug

# Check the converted plugin
agy plugin validate ~/.gemini/config/plugins/daplug --strict
```

To try it without touching your real agy config, install into a throwaway HOME:

```bash
H=$(mktemp -d)
HOME=$H agy plugin install "$PWD"
HOME=$H agy plugin validate "$H/.gemini/config/plugins/daplug" --strict
rm -rf "$H"
```

## What converts

`agy plugin install` detects `.claude-plugin/plugin.json` and stages a converted copy under `~/.gemini/config/plugins/daplug/`:

| Claude Code component | Antigravity result |
|-----------------------|--------------------|
| `commands/*.md` (21) | Skills named `daplug-cmd-<name>` (for example `daplug-cmd-run-prompt`) |
| `skills/*/SKILL.md` (12) | Skills with the same names |
| `agents/*.md` (11) | Custom agents. `tools:` must be a YAML list, which daplug uses |
| `hooks/hooks.json` | Root `hooks.json`. The `Bash` matcher becomes `run_command` |
| `.claude-plugin/plugin.json` | Generated `plugin.json` (name, version, description, author) |

Repo layout rules that keep both loaders happy:

- **Body size.** agy loads only the first 24000 bytes of a skill body. Long reference sections live verbatim in `references/*.md` (for commands) or `skills/<name>/references/*.md` (for skills), and the main file points to them. `scripts/tests/test_agy_compat.py` enforces the limit.
- **Command references stay out of `commands/`.** Claude Code loads every `commands/**/*.md` file as a command, so command references go in the top-level `references/` directory.
- **Generated model regions** that moved into `references/` are still kept in sync by `python3 scripts/manage-models.py generate`.
- **Every skill needs frontmatter** with `name` and `description`, or agy skips it.

## Known limits

- **Agent `model:` tiers.** agy accepts only `inherit`, `flash`, or `pro` in agent frontmatter. Claude Code tiers (`sonnet`, `opus`, `haiku`) make agy skip the agent with `Invalid model tier`. daplug keeps the Claude tiers so Claude Code behavior is unchanged, so agy skips the 11 agents for now. `inherit` is the only value both loaders accept. Switching to it would make agy load the agents, but Claude would then run each agent on the parent session's model instead of its pinned tier.
- **The hook fires only on `run_command`.** The post-push detector runs after shell commands only. agy rewrites the command path to `./hooks/scripts/post-push-detect.sh`, so it resolves relative to the plugin directory.
- **State is shared under `~/.claude`.** Skills and commands still resolve helper scripts through `~/.claude/plugins/installed_plugins.json` and write to `~/.claude/cli-logs/` and `~/.claude/loop-state/`. This is intentional: Claude Code, Hermes, and agy share one set of logs and loop state. So agy-driven runs need the Claude Code plugin installed too, because `$PLUGIN_ROOT` points at the Claude install.
- **No logo in the converted manifest.** `assets/logo.svg` ships with the repo, but the converter writes its own `plugin.json` without a `logo` field. Claude Code's manifest does not reference the logo either, because Claude flags `logo` as an unknown field. `agy plugin validate` shows an info note for this, not a warning.

## No-Google policy

Runs started from agy do not go through `~/.local/bin/daplug-run`, so the executor enforces the no-Google policy itself (`skills/prompt-executor/scripts/google_guard.py`):

- **Protected repos.** A repo is protected when its root path, the `--cwd` directory, or the `origin` URL matches `DAPLUG_NO_GOOGLE_REPOS`. The default pattern is `tldrhq|youtube[_-]?summaries`, matched case-insensitively.
- **Google routes.** These are any model with `routing.google: true` or `default_cli` `agy`/`gemini`, plus `--cli agy|antigravity|gemini`. Every `--moa` entry is checked, and so is a CLI that preferred-agent routing resolves to `agy` or `gemini`.
- **Refusal.** The executor exits with status 2, prints a message on stderr and `{"error": ..., "refused": "no_google_policy"}` on stdout. This happens before any CLI preflight, worktree, or log is created, in preview mode too.
- **Bypass.** `DAPLUG_NO_GOOGLE_REPOS=''` turns the guard off on purpose.
