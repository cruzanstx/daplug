---
name: cclimits
description: Check AI CLI usage/quota for Claude, Codex, Gemini, Z.AI
---

Check remaining quota and usage for AI coding assistants using the [cclimits](https://www.npmjs.com/package/cclimits) npm package.

## Run the Command

```bash
# Compact one-liner (5h window)
npx cclimits --oneline

# Detailed output (all tools)
npx cclimits

# Specific tools only
npx cclimits --claude
npx cclimits --codex
npx cclimits --gemini
npx cclimits --zai

# JSON output (for scripting)
npx cclimits --json
```

## Output

Display the results to the user. Key things to highlight:
- Which tools are connected vs have errors
- Percentage used for each quota window (grouped by tier for Gemini)
- Time until quota resets
- Any warnings about rate limits being reached

If a tool shows "No credentials found", tell the user how to authenticate:
- Claude: Run `claude` to login
- Codex: Run `codex login`
- Gemini: Run `gemini` to login
- Z.AI: Set `ZAI_KEY` environment variable

## Auto-Approve Setup (Optional)

If the user wants to run this command without approval prompts, add to `~/.claude/settings.json` under `permissions.allow`:

```json
"Bash(npx cclimits:*)",
"Bash(cclimits:*)"
```
