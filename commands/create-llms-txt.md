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

Include the appropriate special case section based on library type:

**For Go Libraries:**
```xml
<special_case_instructions>
- Include pkg.go.dev documentation
- Cover interfaces, types, methods
- Show testing patterns
- Include module/import paths
</special_case_instructions>
```

**For JavaScript/TypeScript Libraries:**
```xml
<special_case_instructions>
- Include npm package info
- Cover TypeScript types if applicable
- Show both CommonJS and ESM usage
- Include bundler considerations
</special_case_instructions>
```

**For Python Libraries:**
```xml
<special_case_instructions>
- Include PyPI information
- Cover class hierarchies
- Show async patterns if applicable
- Include virtual environment setup
</special_case_instructions>
```

**For CLI Tools:**
```xml
<special_case_instructions>
- Include installation methods (brew, apt, binary)
- Cover all major commands
- Show configuration file formats
- Include shell completion info
</special_case_instructions>
```

**For Frameworks:**
```xml
<special_case_instructions>
- Cover architecture/philosophy
- Include project structure patterns
- Show lifecycle/hooks
- Include plugin/extension systems
</special_case_instructions>
```

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
All available models for /daplug:run-prompt --model:

**Claude Family:** (check: `claude.five_hour.used`, `claude.seven_day.used`)
- `claude` - Claude sub-agent in current context (best for complex reasoning, multi-step tasks)

**OpenAI Codex Family:** (check: `codex.primary_window.used`, `codex.secondary_window.used`)
- `codex` - gpt-5.3-codex (fast, good for straightforward coding)
- `codex-high` - gpt-5.3-codex with high reasoning
- `codex-xhigh` - gpt-5.3-codex with xhigh reasoning (complex projects)
- `gpt52` - gpt-5.2 (planning, research, analysis)
- `gpt52-high` - gpt-5.2 with high reasoning
- `gpt52-xhigh` - gpt-5.2 with xhigh reasoning (30+ min tasks)

**Google Gemini Family:** (check: `gemini.models.<model>.used` for each)
- `gemini` - Gemini 3 Flash Preview (default, best coding performance)
- `gemini-high` - Gemini 2.5 Pro (higher capability)
- `gemini-xhigh` - Gemini 3 Pro Preview (maximum capability)
- `gemini25pro` - Gemini 2.5 Pro (stable, capable)
- `gemini25flash` - Gemini 2.5 Flash (fast, cost-effective)
- `gemini25lite` - Gemini 2.5 Flash Lite (fastest)
- `gemini3flash` - Gemini 3 Flash Preview (best coding)
- `gemini3pro` - Gemini 3 Pro Preview (most capable)

**Other Models:** (check: `zai.token_quota.percentage`)
- `zai` - Z.AI GLM-4.7 (good for Chinese language tasks)
- `local` - Local model via opencode + LMStudio (no quota limits)
- `qwen` - Qwen via opencode + LMStudio (no quota limits)
- `devstral` - Devstral via opencode + LMStudio (no quota limits)
</available_models>

<recommendation_logic>
For llms.txt research tasks, recommend models in this order (based on availability):

| Priority | Model | Reason |
|----------|-------|--------|
| 1 | gpt52-xhigh | Best for research - deep reasoning, can work 30+ min |
| 2 | gpt52-high | Great for methodical research |
| 3 | gemini25pro | Great at comprehensive research |
| 4 | gemini3pro | Most capable Gemini |
| 5 | claude | Excellent reasoning but uses your quota |
| 6 | codex-xhigh | Good for doc writing after research |
| 7 | zai | Good fallback for documentation |

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
  Claude: {X}% (5h) {status} | Codex: {X}% (5h) {status} | Z.AI: {X}% {status}

  Gemini models:
    3-flash: {X}% {status} | 2.5-pro: {X}% {status} | 3-pro: {X}% {status}
    2.5-flash: {X}% {status} | 2.5-lite: {X}% {status}

  Execute via:

  **Claude:** {usage status}
  1. Claude - sub-agent in current context
  2. Claude (worktree) - isolated git worktree

  **Codex (OpenAI):** {usage status}
  3. codex - gpt-5.3-codex standard
  4. codex-high - higher reasoning
  5. codex-xhigh - maximum reasoning

  **GPT-5.2 (OpenAI):** {usage status} - Best for research/planning
  6. gpt52 - planning, research, analysis
  7. gpt52-high - deep reasoning
  8. gpt52-xhigh - maximum reasoning (30+ min) (Recommended for llms.txt)

  **Gemini (Google):** {show each model's usage}
  9. gemini (3-flash) - {X}% used
  10. gemini25flash - {X}% used
  11. gemini25pro - {X}% used - great for research
  12. gemini3pro - {X}% used - most capable

  **Other:**
  13. zai - {X}% used
  14. local/qwen/devstral - Local models via opencode + LMStudio (no quota)

  [Show recommendation: "Recommended for llms.txt research: gpt52-xhigh --worktree --loop"]
  [If preferred_agent is set and available: "Your preferred agent: {preferred_agent} ✅"]

  **Additional flags (can combine):**
  - `--worktree` - Isolated git worktree (recommended: can work on other things)
  - `--loop` - Auto-retry until verification passes (recommended: ensures quality)
  - `--loop --max-iterations N` - Limit loop retries (default: 3)

  Choose (1-14), or type model with flags (e.g., 'gpt52-xhigh --worktree --loop'): _"

  **Execute based on selection:**

  **Important (llms_txt prompts live outside the current repo):**
  - Prefer invoking with `--prompt-file "$LLMS_TXT_DIR/prompts/{NUMBER}-create-llms-txt-{library-name}.md"` so the executor reads the correct file from any project.
  - If `--worktree` is requested, run from within `$LLMS_TXT_DIR` so the worktree is created off the llms_txt repo. If you're not already there, ask the user to confirm running from that repo.

  If user selects Claude (option 1):
    Invoke via Skill tool: `/daplug:run-prompt {NUMBER} --prompt-file "$LLMS_TXT_DIR/prompts/{NUMBER}-create-llms-txt-{library-name}.md"`

  If user selects Claude worktree (option 2):
    Invoke via Skill tool: `/daplug:run-prompt {NUMBER} --prompt-file "$LLMS_TXT_DIR/prompts/{NUMBER}-create-llms-txt-{library-name}.md" --worktree`

  If user selects any other model (options 3-11):
    Invoke via Skill tool: `/daplug:run-prompt {NUMBER} --prompt-file "$LLMS_TXT_DIR/prompts/{NUMBER}-create-llms-txt-{library-name}.md" --model {selected_model}`
    (Add `--worktree` and/or `--loop` if user requests)

  **User can also type custom model names with flags:**
  - "codex-xhigh --worktree --loop" → `/daplug:run-prompt {NUMBER} --prompt-file "$LLMS_TXT_DIR/prompts/{NUMBER}-create-llms-txt-{library-name}.md" --model codex-xhigh --worktree --loop`
  - "gemini25pro --loop" → `/daplug:run-prompt {NUMBER} --prompt-file "$LLMS_TXT_DIR/prompts/{NUMBER}-create-llms-txt-{library-name}.md" --model gemini25pro --loop`
</action>

## Example Interaction Flows

### Example 1: Basic Library

```
User: "/daplug:create-llms-txt axios"
Assistant:
1. Discovers $LLMS_TXT_DIR
2. Reads $LLMS_TXT_DIR/AGENTS.md
3. Asks: "Which category does axios belong to?" → User selects "javascript"
4. Asks: "Does this need a subdirectory?" → User selects "No subdirectory"
5. Asks: "Any advanced deep-dive files needed?" → User says "No, just the base file"
6. Creates $LLMS_TXT_DIR/prompts/061-create-llms-txt-axios.md
7. Presents execution options
8. User selects "codex-xhigh --worktree --loop"
9. Invokes: /daplug:run-prompt 061 --prompt-file "$LLMS_TXT_DIR/prompts/061-create-llms-txt-axios.md" --model codex-xhigh --worktree --loop
```

### Example 2: With Deep-Dive Files

```
User: "/daplug:create-llms-txt gemini-cli"
Assistant:
1. Discovers $LLMS_TXT_DIR
2. Asks category → "tools"
3. Asks subdirectory → "No subdirectory"
4. Proposes deep-dive files:
   - gemini-cli-configuration-advanced.llms-full.txt
   - gemini-cli-tools-advanced.llms-full.txt
   - gemini-cli-troubleshooting-advanced.llms-full.txt
5. User approves files 1 and 3
6. Creates $LLMS_TXT_DIR/prompts/062-create-llms-txt-gemini-cli.md (includes advanced file instructions)
7. Presents execution options
8. User selects "gemini3pro --worktree"
9. Invokes: /daplug:run-prompt 062 --prompt-file "$LLMS_TXT_DIR/prompts/062-create-llms-txt-gemini-cli.md" --model gemini3pro --worktree
```

### Example 3: Library/Ecosystem Subdirectory

```
User: "/daplug:create-llms-txt bubbletea"
Assistant:
1. Discovers $LLMS_TXT_DIR
2. Asks category → "go"
3. Asks subdirectory → "Library/ecosystem subdirectory"
4. Asks subdirectory name → "charmbracelet"
5. Target: $LLMS_TXT_DIR/go/charmbracelet/bubbletea.llms-full.txt
6. Creates $LLMS_TXT_DIR/prompts/063-create-llms-txt-bubbletea.md
7. User runs with codex-xhigh
```

## Meta Instructions

- If the library name is ambiguous, ask for clarification before proceeding
- Always determine target path BEFORE creating the prompt
- The generated prompt should be self-contained and executable by any model
- Include verification section so `--loop` can work properly
- Recommend `--worktree` for isolation (user can continue working on other things)
- Recommend `--loop` to ensure quality (auto-retries if verification fails)
- For multiple libraries at once, create multiple prompts and suggest `--parallel`
