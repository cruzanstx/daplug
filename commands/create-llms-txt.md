---
name: create-llms-txt
description: Research a library/topic and generate comprehensive llms_txt documentation
argument-hint: <library-name>
---

# LLMS.txt Documentation Generator

You are tasked with gathering requirements for llms_txt documentation and creating an executable prompt that can be run via `/run-prompt`.

## User Request

The user wants to create llms_txt documentation for: $ARGUMENTS

## Process Overview

<objective>
Gather all necessary information (target directory, category, subdirectory, deep-dive topics) and generate a comprehensive prompt file that can be executed via `/run-prompt` with any model.
</objective>

## Step 0: Determine Target Directory

Before starting, determine the llms_txt repository location:

**1. Check for existing setting in `~/.claude/CLAUDE.md`:**
```bash
PLUGIN_ROOT=$(jq -r '.plugins."daplug@cruzanstx"[0].installPath' ~/.claude/plugins/installed_plugins.json)
CONFIG_READER="$PLUGIN_ROOT/skills/config-reader/scripts/config.py"

LLMS_TXT_DIR=$(python3 "$CONFIG_READER" get llms_txt_dir)
if [ -z "$LLMS_TXT_DIR" ] || [ ! -d "$LLMS_TXT_DIR" ]; then
    # Proceed to AskUserQuestion (Step 2)
    :
fi
```

**2. If not found OR directory does not exist:**

Use AskUserQuestion tool:
- Question: "Where is your llms_txt documentation repository?"
- Header: "llms_txt repo"
- Options:
  1. **Clone repository** (Recommended)
     - Description: "Clone from gitlab.local/local/llms_txt.git"
  2. **Specify existing path**
     - Description: "Enter path to your existing llms_txt repo"
  3. **Create new directory**
     - Description: "Create a new llms_txt directory structure"

**3. If user chooses "Clone repository":**
```bash
# Determine sensible default location
if [[ "$PWD" == /storage/projects/* ]]; then
    DEFAULT_CLONE_DIR="/storage/projects/docker/llms_txt"
else
    DEFAULT_CLONE_DIR="$HOME/projects/llms_txt"
fi

# Ask user to confirm or customize location, then set:
# LLMS_TXT_DIR="<user-chosen-path>"

# Clone the repo
git clone https://gitlab.local/local/llms_txt.git "$LLMS_TXT_DIR"

# Verify success
if [ -f "$LLMS_TXT_DIR/AGENTS.md" ] || [ -f "$LLMS_TXT_DIR/DOCUMENTATION-INDEX.md" ]; then
    echo "✓ Repository cloned successfully"
else
    echo "⚠ Clone may have failed - missing expected files"
fi
```

**4. If user chooses "Specify existing path":**
```bash
LLMS_TXT_DIR="<user-provided-path>"
if [ ! -d "$LLMS_TXT_DIR" ]; then
    echo "⚠ Path does not exist. Ask again or offer Create new directory."
fi
```

**5. If user chooses "Create new directory":**
```bash
LLMS_TXT_DIR="<user-provided-path>"
mkdir -p "$LLMS_TXT_DIR/prompts/completed"
```

**6. Save setting to `~/.claude/CLAUDE.md`:**
```bash
python3 "$CONFIG_READER" set llms_txt_dir "$LLMS_TXT_DIR" --scope user
```

**7. All prompts will be created in:** `$LLMS_TXT_DIR/prompts/`

**8. Read the repository structure**:
   - Read `$LLMS_TXT_DIR/AGENTS.md` to understand the directory organization
   - Examine existing subdirectories to see where similar libraries are located

**9. Determine the language/category**:
   - Ask the user which category this library belongs to:
     - `python/` - Python libraries and frameworks
     - `go/` - Go libraries and tools
     - `javascript/` - JavaScript libraries
     - `typescript/` - TypeScript frameworks
     - `frameworks/` - Cross-platform frameworks
     - `tools/` - Development tools (CLI, editors, etc.)

**10. Check for subdirectories**:
   - Within the chosen category, determine if a subdirectory is needed
   - Subdirectories can be:
     - **Category-based**: For grouping similar types (e.g., `python/ai/`, `go/cli/`, `go/testing/`)
     - **Library-based**: For multiple related files from the same library/ecosystem (e.g., `python/pydantic_ai/`, `go/charmbracelet/`, `frameworks/pocketbase/`)
   - Ask the user if a subdirectory is needed and what type:
     - Category subdirectory (ai, web, cli, testing, terminal, database, logging, etc.)
     - Library/ecosystem subdirectory (when multiple related files exist for that library)
     - No subdirectory (file goes directly in the language folder)

**11. Construct the full path**:
   - Base: `$LLMS_TXT_DIR/`
   - Language/Category: `<language>` or `<tools/frameworks>`
   - Subdirectory (optional): `<category-or-library>/`
   - File: `<library-name>.llms-full.txt`

## Step 0.5: Deep-Dive Scoping

Before writing the prompt, propose an **advanced deep-dive file set** when useful:

1. **Scan official docs quickly** to identify high-value advanced topics (e.g., configuration, CLI reference, plugins/extensions, MCP/tooling, hooks, troubleshooting, auth, output formats, integrations).

2. **Propose a focused list** of advanced files with rationale and filenames.

3. **Ask for user approval** and confirmation on:
   - Which advanced files to create
   - Naming pattern (e.g., `tool-name-advanced.llms-full.txt` or `tool-name-<topic>-advanced.llms-full.txt`)
   - Whether to create advanced files **in addition to** the base file

4. **Only include advanced files in the prompt** after user confirms.

**Deep-Dive Naming Guidance**
- Use `-advanced` suffix for topic-specific deep dives.
- Prefer multiple focused files over one huge advanced file.
- Examples:
  - `gemini-cli-configuration-advanced.llms-full.txt`
  - `gemini-cli-tools-advanced.llms-full.txt`
  - `gemini-cli-mcp-advanced.llms-full.txt`

**Deep-Dive Proposal Checklist**
- Pick 4–8 advanced topics max (avoid dilution).
- Ensure each topic is meaningfully distinct.
- Include at least one "operational" topic (troubleshooting, performance, security, telemetry, or CI usage).
- Include at least one "interface" topic (CLI reference, config, output formats).
- Only include plugins/extensions if the product officially supports them.

## Step 1: Generate Prompt File

After gathering all information, create a prompt file in `$LLMS_TXT_DIR/prompts/`:

### Determine Next Prompt Number

```bash
# Find highest existing number in llms_txt prompts directory
NEXT_NUM=$(ls "$LLMS_TXT_DIR/prompts/"*.md "$LLMS_TXT_DIR/prompts/completed/"*.md 2>/dev/null | sed 's|.*/||' | grep -oE '^[0-9]{3}' | sort -n | tail -1)
if [ -z "$NEXT_NUM" ]; then
    NEXT_NUM="001"
else
    NEXT_NUM=$(printf "%03d" $((10#$NEXT_NUM + 1)))
fi
```

### Create Prompt File

Save to `$LLMS_TXT_DIR/prompts/{NEXT_NUM}-create-llms-txt-{library-name}.md`:

```markdown
<objective>
Research {LIBRARY_NAME} thoroughly and generate a comprehensive, well-structured llms_txt file that provides all essential information an AI assistant would need to work with this technology.
</objective>

<target_file>
{FULL_PATH} (e.g., {LLMS_TXT_DIR}/{category}/{subdirectory}/{library-name}.llms-full.txt)
</target_file>

<research_phase>
1. **Check for existing llms.txt files**:
   - Search for official llms.txt or llms-full.txt files from the library's website
   - Check GitHub repositories for existing documentation
   - Look for community-maintained llms.txt files

2. **Gather primary sources**:
   - Official documentation (GitHub README, docs site)
   - Package/API documentation (pkg.go.dev, npm, PyPI, etc.)
   - Comprehensive guides from reputable sources (Better Stack, official tutorials)

3. **Use WebSearch and WebFetch**:
   ```
   WebSearch: "{LIBRARY_NAME} llms.txt"
   WebSearch: "{LIBRARY_NAME} official documentation"
   WebSearch: "{LIBRARY_NAME} complete guide tutorial"
   ```

4. **Fetch comprehensive content**:
   - Official GitHub repository README
   - Official documentation site
   - 1-2 high-quality tutorial/guide sites
   - API reference documentation

**Research priorities:**
- Official sources (GitHub, official docs)
- Comprehensive guides (Better Stack, LogRocket, etc.)
- API/package documentation sites
- Well-maintained community resources

**Extract:**
- All features and capabilities
- Installation and setup instructions
- Complete API reference with types/methods
- Usage examples and patterns
- Best practices and performance considerations
- Common patterns and anti-patterns
- Configuration options
- Integration examples
</research_phase>

<content_structure>
Structure the llms_txt file with these sections:

```markdown
# {LIBRARY_NAME} - [One-line Description]

> Official Repository: [URL]
> Documentation: [URL]
> Version: [Latest stable version]
> License: [License type]

## Overview

[What it is, what problems it solves, key philosophy]

## Installation

[Package manager commands, setup steps]

## Core Features

[Bullet list of main capabilities]

## Basic Usage

### [Feature 1]
[Code examples with explanations]

### [Feature 2]
[Code examples with explanations]

## Advanced Features

### [Advanced Feature 1]
[Detailed examples]

### [Advanced Feature 2]
[Detailed examples]

## Configuration

[Environment variables, config files, options]

## Best Practices

[Performance tips, recommended patterns, what to avoid]

## Critical Implementation Notes

[Important gotchas, common mistakes, must-know information]

## Common Patterns

[Real-world usage examples]

## Comparison/Context

[How it compares to alternatives, when to use it]

## Resources

- Official links
- Community resources
- Related tools

---

**Generated**: [Date]
**Source**: [List of primary sources]
**Maintainer**: [Original author/org]
```
</content_structure>

<quality_requirements>
1. **Comprehensive**: Cover all major features and use cases
2. **Code-heavy**: Include 30-50+ practical code examples
3. **Practical**: Focus on real-world usage patterns
4. **Accurate**: Use only verified information from official sources
5. **Well-structured**: Clear hierarchy with searchable headings
6. **Self-contained**: Should be useful without external references
7. **Examples first**: Show usage before explaining theory
8. **Critical notes**: Highlight gotchas, common mistakes, performance tips
9. **Up-to-date**: Use latest stable version information
10. **Reference-quality**: Include all types, methods, configuration options
</quality_requirements>

{IF_ADVANCED_FILES}
<advanced_files>
Also create these advanced deep-dive files:
{LIST_OF_ADVANCED_FILES_WITH_TOPICS}

Each advanced file should:
- Focus deeply on its specific topic
- Include 20+ code examples for that topic
- Cover edge cases and advanced configurations
- Follow the same quality requirements
</advanced_files>
{/IF_ADVANCED_FILES}

<special_case_instructions>
{SPECIAL_CASE_CONTENT - see templates below}
</special_case_instructions>

<verification>
Before declaring complete, verify:
- [ ] File saved to {FULL_PATH}
- [ ] Directory structure matches existing organization
- [ ] Includes overview, installation, core features
- [ ] Contains 30+ code examples covering major use cases
- [ ] Documents all important types/methods/functions
- [ ] Includes configuration options
- [ ] Contains best practices and gotchas
- [ ] Lists all source URLs
- [ ] Well-formatted markdown with clear hierarchy
- [ ] Covers both basic and advanced usage
- [ ] Includes comparison/context section if applicable

Output: <verification>VERIFICATION_COMPLETE</verification>
</verification>
```

### Special Case Templates

Include the matching `<special_case_instructions>` block (Go, JavaScript/TypeScript, Python, CLI tools, frameworks) from `$PLUGIN_ROOT/references/create-llms-txt-special-case-templates.md` (`PLUGIN_ROOT` is resolved in Step 0).

## Step 2: Report and Offer Execution

After creating the prompt file, present the decision tree:

<detection_logic>
Before presenting options:

1. **Check ai_usage_awareness setting** (feature flag):
   ```bash
   PLUGIN_ROOT=$(jq -r '.plugins."daplug@cruzanstx"[0].installPath' ~/.claude/plugins/installed_plugins.json)
   CONFIG_READER="$PLUGIN_ROOT/skills/config-reader/scripts/config.py"

   AI_USAGE_AWARENESS=$(python3 "$CONFIG_READER" get ai_usage_awareness)
   ```

   **If setting not found in either location:**
   Ask the user:
   "Would you like to enable AI usage awareness? This shows quota percentages for each model and suggests alternatives when models are near their limits.

   1. Yes, enable it (recommended)
   2. No, disable it

   Choose (1-2): _"

   Based on response, set in `~/.claude/CLAUDE.md` under `<daplug_config>`:
   - If yes: `ai_usage_awareness: enabled`
   - If no: `ai_usage_awareness: disabled`

   ```bash
   python3 "$CONFIG_READER" set ai_usage_awareness "enabled" --scope user
   # or
   python3 "$CONFIG_READER" set ai_usage_awareness "disabled" --scope user
   ```

   **If setting is "disabled":** Skip step 2, don't show usage info, proceed directly to step 3.

2. **Check AI CLI usage** (only if ai_usage_awareness is enabled or unset-but-user-said-yes):
   ```bash
   npx cclimits --json 2>/dev/null
   ```

   Parse the JSON to extract usage percentages:
   - `claude`: Check `claude.five_hour.used` and `claude.seven_day.used`
   - `codex`: Check `codex.primary_window.used` and `codex.secondary_window.used`
   - `gemini`: Check `gemini.models.*` for each model's usage
   - `zai`: Check `zai.token_quota.percentage`
   - `synthetic`: If cclimits exposes it, check `synthetic.subscription.requests / synthetic.subscription.limit`; otherwise note `GET https://api.synthetic.new/v2/quotas` with `SYNTHETIC_API_KEY`

   **Usage thresholds:**
   - `< 70%` → Available (show normally)
   - `70-90%` → Warning (show with ⚠️)
   - `> 90%` → Near limit (show with 🔴)
   - `100%` or error → Unavailable (show with ❌, skip in recommendations)

3. **Read preferred_agent** from `<daplug_config>` in CLAUDE.md:
   ```bash
   PREFERRED_AGENT=$(python3 "$CONFIG_READER" get preferred_agent)
   PREFERRED_AGENT=${PREFERRED_AGENT:-claude}
   ```
</detection_logic>

<available_models>
The full generated model table for `/daplug:run-prompt --model` lives in `$PLUGIN_ROOT/references/create-llms-txt-available-models.md`. Read it when you need a model's description or availability notes.
</available_models>

<recommendation_logic>
For llms.txt research tasks, recommend models in this order (based on availability):

<!-- BEGIN GENERATED: create-llms-recommendations -->
| Priority | Model | Reason |
|----------|-------|--------|
| 1 | gpt52-xhigh | Best for research - deep reasoning, can work 30+ min |
| 2 | gpt52-high | Great for methodical research |
| 3 | gpt55-high | Fast, high-quality synthesis after research |
| 4 | gemini31pro | Most capable Gemini for research (if available) |
| 5 | gemini25pro | Great at comprehensive research |
| 6 | gemini3pro | Strong Gemini fallback |
| 7 | claude | Excellent reasoning but uses your quota |
| 8 | codex-xhigh | Good for doc writing after research |
| 9 | synthetic | GLM-5.2 via Synthetic with request-count quota |
| 10 | kimi | Strong OpenCode fallback for long-form drafting |
| 11 | glm52 | GLM-5.2 explicit pin with 1M context |
| 12 | glm5 | Latest GLM 5.x alias for GLM-5.2 |
| 13 | zai | Good fallback for documentation |
<!-- END GENERATED: create-llms-recommendations -->

**Recommended flags for llms.txt:**
- `--worktree` - Isolate the work (can continue working on other things)
- `--loop` - Auto-retry if verification fails (ensures quality)

If `preferred_agent` is set AND available, show it as first option.
</recommendation_logic>

<presentation>
✓ Saved prompt to $LLMS_TXT_DIR/prompts/{NUMBER}-create-llms-txt-{library-name}.md

**Target output:** {FULL_PATH}
{IF_ADVANCED: Also creating: {LIST_OF_ADVANCED_FILES}}

What's next?

1. Run prompt now
2. Review/edit prompt first
3. Save for later
4. Other

Choose (1-4): _
</presentation>

<action>
If user chooses #1:
  First, run cclimits to get current quota status:
  ```bash
  npx cclimits --json 2>/dev/null
  ```

  Then present executor options with usage status:

  "📊 **AI Quota Status:**
  Claude: {X}% (5h) {status} | Codex: {X}% (5h) {status} | Z.AI: {X}% {status} | Synthetic: {requests}/{limit} requests {status}

  Gemini models:
    3-flash: {X}% {status} | 2.5-pro: {X}% {status} | 3-pro: {X}% {status} | 3.1-pro: {X}% {status}
    2.5-flash: {X}% {status} | 2.5-lite: {X}% {status}

  Execute via:

<!-- BEGIN GENERATED: create-llms-selection-menu -->
  **Claude:** {usage status}
  1. claude - sub-agent in current context
  2. cc-sonnet - Claude Code CLI Sonnet 5.5
  3. cc-opus - floating Opus alias, currently Opus 5.5
  4. fable - floating Fable alias, currently Fable 5.2
  5. fable52 - Fable 5.2 explicit pin, 1M context
  6. fable51 - Fable 5.1 explicit pin, 1M context

  **Codex (OpenAI):** {usage status}
  7. codex - {X}% used - gpt-5.6-terra standard
  8. codex-spark - {X}% used - fast/low-cost coding tier
  9. codex-high - {X}% used - higher reasoning
  10. codex-xhigh - {X}% used - maximum reasoning
  11. sol - {X}% used - gpt-6.2-sol frontier tier
  12. terra - {X}% used - gpt-5.6-terra balanced tier
  13. luna - {X}% used - gpt-6-luna fast/affordable tier
  14. astra - {X}% used - gpt-6.2-astra explicit shorthand
  15. gpt54 - {X}% used - gpt-5.4 explicit shorthand
  16. gpt54-high - {X}% used - deep reasoning
  17. gpt54-xhigh - {X}% used - maximum reasoning
  18. gpt55 - {X}% used - gpt-5.5 explicit shorthand
  19. gpt55-high - {X}% used - deep reasoning
  20. gpt55-xhigh - {X}% used - maximum reasoning
  21. gpt52 - {X}% used - planning, research, analysis
  22. gpt52-high - {X}% used - deep reasoning
  23. gpt52-xhigh - {X}% used - maximum reasoning (30+ min tasks)

  **Gemini (Google):** {show each model's usage}
  24. gemini - {X}% used - 3.8-flash High via Antigravity, default Gemini shorthand
  25. gemini-high - {X}% used - 2.5-pro
  26. gemini-xhigh - {X}% used - 3-pro preview
  27. gemini25pro - {X}% used - 2.5-pro, stable/capable
  28. gemini25flash - {X}% used - 2.5-flash, fast/cost-effective
  29. gemini25lite - {X}% used - 2.5-flash-lite, fastest
  30. gemini3flash - {X}% used - 3-flash explicit
  31. gemini3pro - {X}% used - 3-pro, most capable
  32. gemini31pro - {X}% used - 3.1 Pro Preview if available
  33. gemini37 - {X}% used - 3.8-flash High, default 3.7 Flash alias
  34. gemini37-high - {X}% used - 3.8-flash High, latest deep reasoning
  35. gemini37-medium - {X}% used - 3.8-flash Medium, latest balanced Flash
  36. gemini37-low - {X}% used - 3.8-flash Low, latest fast tier
  37. argon - {X}% used - Argon High, AGY only
  38. argon-high - {X}% used - Argon High, AGY only
  39. argon-medium - {X}% used - Argon Medium, AGY only
  40. argon-low - {X}% used - Argon Low, AGY only
  41. carbon - {X}% used - Carbon High, AGY only
  42. carbon-high - {X}% used - Carbon High, AGY only
  43. carbon-medium - {X}% used - Carbon Medium, AGY only
  44. carbon-low - {X}% used - Carbon Low, AGY only
  45. hydrogen - {X}% used - Hydrogen High, AGY only
  46. hydrogen-xhigh - {X}% used - Hydrogen XHigh, AGY only
  47. hydrogen-high - {X}% used - Hydrogen High, AGY only
  48. hydrogen-medium - {X}% used - Hydrogen Medium, AGY only
  49. hydrogen-low - {X}% used - Hydrogen Low, AGY only
  50. neon - {X}% used - Neon High, AGY only
  51. neon-xhigh - {X}% used - Neon XHigh, AGY only
  52. neon-high - {X}% used - Neon High, AGY only
  53. neon-medium - {X}% used - Neon Medium, AGY only
  54. neon-low - {X}% used - Neon Low, AGY only
  55. agy - {X}% used - 3.8-flash High, default agy shorthand

  **Z.AI / OpenCode:** {usage status}
  56. zai - {X}% used - Z.AI GLM-4.7
  57. glm5 - {X}% used - Z.AI GLM-5.3 latest alias
  58. glm52 - {X}% used - Z.AI GLM-5.2 explicit pin
  59. glm53 - {X}% used - Z.AI GLM-5.3 explicit pin
  60. flash - {X}% used - Z.AI GLM-5.3-Flash multimodal, 3x quota, reasoning max
  61. glm53-flash - {X}% used - Z.AI GLM-5.3-Flash versioned alias of flash
  62. kimi - {X}% used - Kimi K2.5 via OpenCode
  63. opencode - {X}% used - OpenCode GLM-4.7

  **Synthetic:** {usage status}
  64. synthetic - {requests}/{limit} requests - Synthetic floating (currently DS V4.1 Flash)
  65. syn-flash - {requests}/{limit} requests - Synthetic floating (currently GLM-4.7-Flash)
  66. syn-kimi - {requests}/{limit} requests - Synthetic floating (currently Kimi-K3) vision
  67. syn-kimi3 - {requests}/{limit} requests - Synthetic Kimi-K3 vision
  68. syn-qwen - {requests}/{limit} requests - Synthetic floating (currently Qwen3.8-27B) vision
  69. syn-minimax - {requests}/{limit} requests - Synthetic MiniMax-M3 vision
  70. syn-nemotron - {requests}/{limit} requests - Synthetic Nemotron-3-Super
  71. syn-glm53 - {requests}/{limit} requests - Synthetic GLM-5.3 beta text-only
  72. syn-glm53-flash - {requests}/{limit} requests - Synthetic GLM-5.3-Flash beta vision
  73. syn-ds41-flash - {requests}/{limit} requests - Synthetic DeepSeek V4.1 Flash vision
  74. deepseek - {requests}/{limit} requests - Synthetic DeepSeek V4.1 Flash (alias of syn-ds41-flash)

  **Local:** {usage status}
  75. local - local qwen3.6-35b-a3b, no quota
  76. qwen - local qwen3.6-35b-a3b, no quota
  77. devstral - local Devstral, no quota
  78. glm-local - local GLM-4.7 Flash, no quota
  79. qwen-small - local qwen3-4b, no quota
  80. qwen36 - local qwen3.6-35b-a3b, no quota
  81. qwen36-27b - local qwen3.6-27b, no quota

  Choose (1-81), or type model with flags (e.g., 'codex --worktree --loop'): _
<!-- END GENERATED: create-llms-selection-menu -->

  **Execute based on selection:**

  **Important (llms_txt prompts live outside the current repo):**
  - Prefer invoking with `--prompt-file "$LLMS_TXT_DIR/prompts/{NUMBER}-create-llms-txt-{library-name}.md"` so the executor reads the correct file from any project.
  - If `--worktree` is requested, run from within `$LLMS_TXT_DIR` so the worktree is created off the llms_txt repo. If you're not already there, ask the user to confirm running from that repo.

  After selection:
  - If the user typed model flags, append those flags after the `--prompt-file` argument.
  - If the user selected a listed model, invoke `/daplug:run-prompt {NUMBER} --prompt-file "$LLMS_TXT_DIR/prompts/{NUMBER}-create-llms-txt-{library-name}.md" --model {selected_model}`.
  - If the selected model is `claude`, `--model claude` may be omitted, but keeping it is valid.
  - Add `--worktree` and/or `--loop` if the user requests them.

  **User can also type custom model names with flags:**
  - "codex-xhigh --worktree --loop" → append `--model codex-xhigh --worktree --loop`
  - "gemini25pro --loop" → append `--model gemini25pro --loop`
</action>

## Example Interaction Flows

Worked examples (basic library, deep-dive files, ecosystem subdirectory) are in `$PLUGIN_ROOT/references/create-llms-txt-examples.md`.

## Meta Instructions

- If the library name is ambiguous, ask for clarification before proceeding
- Always determine target path BEFORE creating the prompt
- The generated prompt should be self-contained and executable by any model
- Include verification section so `--loop` can work properly
- Recommend `--worktree` for isolation (user can continue working on other things)
- Recommend `--loop` to ensure quality (auto-retries if verification fails)
- For multiple libraries at once, create multiple prompts and suggest `--parallel`
