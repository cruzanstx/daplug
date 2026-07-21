---
name: ai-usage
description: Check AI CLI usage/quota for Claude Code, OpenAI Codex, Google Gemini CLI, Z.AI, and Synthetic. Use when user asks about remaining quota, usage limits, rate limits, or wants to check how much capacity is left.
allowed-tools:
  - Bash(npx cclimits:*)
  - Bash(cclimits:*)
---

# AI CLI Usage Checker

Check remaining quota and usage for AI coding assistants: Claude Code, OpenAI Codex, Gemini CLI, Z.AI, and Synthetic.

Uses the [cclimits](https://www.npmjs.com/package/cclimits) npm package.

## When to Use This Skill

- User asks "how much quota do I have left?"
- User asks "check my usage" or "am I rate limited?"
- User wants to know which AI tool has capacity
- Before starting a large task, to verify quota availability
- User asks about token limits or remaining requests

## Running the Command

```bash
# Check all tools (detailed)
npx cclimits

# Compact one-liner (5h window)
npx cclimits --oneline

# Compact one-liner (7d window)
npx cclimits --oneline 7d

# One-liner with reset countdowns (alias: --timeremaining)
npx cclimits --oneline both --resets

# Check specific tools
npx cclimits --claude
npx cclimits --codex
npx cclimits --gemini
npx cclimits --zai

# Synthetic direct quota probe (does not count against quota)
curl -H "Authorization: Bearer $SYNTHETIC_API_KEY" https://api.synthetic.new/v2/quotas

# JSON output (for scripting)
npx cclimits --json
```

## Credential Locations

Credentials are auto-discovered from these locations:

| Tool | Location |
|------|----------|
| **Claude** | `~/.claude/.credentials.json` (Linux) or macOS Keychain |
| **Codex** | `~/.codex/auth.json` |
| **Gemini** | `~/.gemini/oauth_creds.json` (auto-refreshes) |
| **Z.AI** | `$ZAI_KEY` or `$ZAI_API_KEY` environment variable |
| **Synthetic** | `$SYNTHETIC_API_KEY` environment variable |

## Setup (One-Time)

If credentials are missing, run the corresponding CLI tool to authenticate:

```bash
claude           # Login to Claude Code
codex login      # Login to OpenAI Codex
gemini           # Login to Gemini CLI
export ZAI_KEY=your-key  # Add to ~/.zshrc
export SYNTHETIC_API_KEY=your-key  # Get from https://synthetic.new dashboard
```

## Output Interpretation

### Quota Windows

Most tools use rolling windows:
- **5-hour window**: Short-term rate limit
- **7-day window**: Weekly quota limit

### Percentage Used

- **0-50%**: Plenty of capacity
- **50-70%**: Moderate usage, plan accordingly
- **70-90%**: High usage, may want to switch tools
- **90-100%**: Near limit, expect rate limiting

### Status Icons

| Icon | Meaning |
|------|---------|
| ✅ | Under 70% - plenty of capacity |
| ⚠️ | 70-90% - moderate usage |
| 🔴 | 90-100% - near limit |
| ❌ | 100% or unavailable |

### Gemini Tiers

Gemini models are grouped by quota tier (models in same tier share quota):

| Tier | Models |
|------|--------|
| **3-Flash** | gemini-3-flash-preview |
| **Flash** | gemini-2.5-flash, gemini-2.5-flash-lite, gemini-2.0-flash |
| **Pro** | gemini-2.5-pro, gemini-3-pro-preview |

## Example Output

### Compact One-liner (--oneline)

```
Claude: 4.0% (5h) ✅ | Codex: 0% (5h) ✅ | Z.AI: 1% ✅ | Gemini: ( 3-Flash 7% ✅ | Flash 1% ✅ | Pro 10% ✅ )
```

With `--resets` (or `--timeremaining`), each provider gains a `↻` reset countdown (`5h-reset/7d-reset` for `both`):

```
Claude: 4.0%/10.0% ✅ ↻2h15m/3d17h | Codex: 0%/2% ✅ ↻1h05m/6d23h | Z.AI: 1% (5h) ✅ ↻3h02m | Antigravity: 3% (20 models) ✅ ↻10m
```

### Detailed Output (default)

```
🔍 AI CLI Usage Checker
   2025-12-31 21:30:00

==================================================
  Claude Code
==================================================
  🔑 Auth: Bearer token
  ✅ Connected

  5-Hour Window:
    Used:      15.2%
    Remaining: 84.8%
    Resets in: 3h 24m

  7-Day Window:
    Used:      42.0%
    Remaining: 58.0%
    Resets in: 4d 12h

==================================================
  OpenAI Codex
==================================================
  🔑 Auth: OAuth (ChatGPT)
  ✅ Connected
  📊 Plan: pro

  5h Window:
    Used:      8%
    Remaining: 92%
    Resets in: 2h 15m

==================================================
  Gemini CLI
==================================================
  🔑 Auth: OAuth (Google Account)
  ✅ Connected
  📊 Tier: standard

  Quota by Tier:
    3-Flash: 7.0% used, 93.0% remaining
    Flash: 1.0% used, 99.0% remaining
    Pro: 10.0% used, 90.0% remaining

==================================================
  Z.AI (GLM-4)
==================================================
  ✅ Connected

  Token Quota:
    Used:      1%
    Remaining: 99%
    (10,000 / 1,000,000 tokens)
```

## Troubleshooting

**"No credentials found"**
- Run the CLI tool to authenticate (see Setup section)
- For Z.AI, ensure environment variable is set

**"Token expired"**
- Claude: Run `claude` to re-authenticate
- Codex: Run `codex login`
- Gemini: Run `gemini` (or wait for auto-refresh)

**API errors**
- Check internet connectivity
- Verify the CLI tool works directly
- Check if the service is down

## Package Info

**npm package:** [cclimits](https://www.npmjs.com/package/cclimits)
**GitHub:** [cruzanstx/cclimits](https://github.com/cruzanstx/cclimits)

Requires: Node.js 16+ and Python 3.10+
