<objective>
Research all CLI coding agents and local model providers before implementation.
Check existing llms_txt documentation, fill gaps with /create-llms-txt, then update
the agent-detection prompts with findings.
</objective>

<context>
**Run this FIRST** before any other agent-detection prompts.

This prompt builds the knowledge base we need to implement detection correctly.
Without solid documentation on each CLI's config format, API, and invocation pattern,
we'll be guessing during implementation.

**Target llms_txt directory**: Check daplug config for `llms_txt_dir` setting.
</context>

<research_targets>
## Tier 1 CLIs (Must Have)

| CLI | Expected Doc | What We Need |
|-----|--------------|--------------|
| Claude Code | `tools/claude-code.llms-full.txt` | Config location, settings format, model list |
| Codex CLI | `tools/codex-cli.llms-full.txt` | Config format, permissions, model flags |
| Gemini CLI | `tools/gemini-cli.llms-full.txt` | Config, auth, model selection |
| OpenCode | `tools/opencode.llms-full.txt` | Config format, permission system, providers |

## Tier 2 CLIs (Should Have)

| CLI | Expected Doc | What We Need |
|-----|--------------|--------------|
| Goose | `tools/goose.llms-full.txt` | Installation, config, supported models |
| Aider | `tools/aider.llms-full.txt` | Installation, config, model support |
| GitHub Copilot CLI | `tools/gh-copilot.llms-full.txt` | `gh copilot` commands, auth |

## Local Model Providers

| Provider | Expected Doc | What We Need |
|----------|--------------|--------------|
| Ollama | `tools/ollama.llms-full.txt` | API endpoints, model listing, health check |
| LMStudio | `tools/lmstudio.llms-full.txt` | API compatibility, model listing endpoint |

## Tier 3 (Research Only)

| CLI | Expected Doc | Notes |
|-----|--------------|-------|
| Factory Droid | `tools/factory-droid.llms-full.txt` | What is this? Research needed |
| Crush | `tools/crush.llms-full.txt` | What is this? Research needed |
| Mentat | `tools/mentat.llms-full.txt` | Viability assessment |
| Amazon Q | `tools/amazon-q.llms-full.txt` | AWS CLI integration |
| Cody | `tools/cody.llms-full.txt` | Sourcegraph CLI capabilities |
</research_targets>

<workflow>
## Phase 1: Audit Existing Documentation

```bash
# Check what we already have
cd $LLMS_TXT_DIR
ls -la tools/*.llms-full.txt | grep -E "(claude|codex|gemini|opencode|goose|aider|copilot|ollama|lmstudio)"
```

Create checklist of what exists vs what's missing.

## Phase 2: Fill Documentation Gaps

For EACH missing doc, run in the llms_txt repository:

```bash
# Example for Ollama
/create-llms-txt ollama

# Example for Goose
/create-llms-txt goose
```

**Priority order** (stop if time/quota constrained):
1. Ollama (needed for local model detection)
2. LMStudio (needed for local model detection)
3. Goose (popular Tier 2)
4. Aider (popular Tier 2)
5. Factory Droid / Crush (research what these are)

## Phase 3: Extract Key Information

After docs are created, extract these details for each CLI:

```markdown
### [CLI Name]

**Installation Detection:**
- Executable name(s):
- Common install paths:
- Version command:

**Config:**
- Config path(s):
- Config format: (JSON/YAML/TOML/env)
- Key settings for daplug:

**Models:**
- How to list available models:
- Default model:
- Cross-provider support: (yes/no, which providers)

**Invocation:**
- Basic command pattern:
- Stdin vs arg for prompt:
- Headless/non-interactive flags:

**API (for providers):**
- Health check endpoint:
- Model list endpoint:
- OpenAI-compatible: (yes/no)
```

## Phase 4: Update Agent-Detection Prompts

**IMPORTANT**: Actually EDIT these prompt files with your research findings.
Do not just document - modify the prompts so they contain real, researched values.

### 4.1 Edit `013-agent-detection-architecture.md`

Replace placeholder/example values with researched facts:
- Update the "Note on Local Models" section with actual Ollama/LMStudio API endpoints
- Fill in the model routing matrix with real model names and CLI capabilities
- Update cache schema example with real config paths discovered

### 4.2 Edit `014-implement-cli-detection.md`

Add concrete implementation details:
- In plugin requirements, add actual executable names (e.g., `["codex"]`, `["gemini"]`)
- Add real config paths (e.g., `~/.codex/config.json`, `~/.config/gemini/...`)
- Add actual version commands (e.g., `codex --version`)

### 4.3 Edit `016-config-templates-fixing.md`

Replace template placeholders with working configs:
- Update codex.json template with real schema
- Update opencode.json template with real permission format
- Add gemini config template based on research

### 4.4 Edit `017-tier2-cli-plugins.md`

Fill in researched details for Tier 2 CLIs:
- Goose: actual config location, supported models, invocation pattern
- Aider: actual config location, model flags, repo URL
- GH Copilot: actual `gh copilot` subcommands and capabilities
</workflow>

<verification>
After completing research:

- [ ] All Tier 1 CLIs have llms_txt documentation
- [ ] At least 2 Tier 2 CLIs documented (Goose, Aider)
- [ ] Both local providers documented (Ollama, LMStudio)
- [ ] Key info extracted for each (config path, format, invocation)
- [ ] Prompts 013, 014, 016, 017 EDITED with real values (not just documented)

**Verify edits were made:**
```bash
# Check that prompts were modified (should show recent timestamps)
ls -la prompts/agent-detection/01[3-7]*.md

# Grep for placeholder text that should have been replaced
grep -l "TBD\|placeholder\|example\.com" prompts/agent-detection/*.md
# (should return empty if all placeholders replaced)
```
</verification>

<success_criteria>
- [ ] Audit complete with gap list
- [ ] At least 6 new/updated llms_txt docs created
- [ ] Research summary written to `./docs/agent-detection-research.md`
- [ ] Prompt 013 edited: real config paths, API endpoints, model routing
- [ ] Prompt 014 edited: actual executable names, version commands
- [ ] Prompt 016 edited: working config templates (not placeholders)
- [ ] Prompt 017 edited: Goose/Aider/GH Copilot real details
- [ ] Ready to begin implementation with solid foundation
</success_criteria>

<output>
Create `./docs/agent-detection-research.md` with:

1. **Documentation Audit** - What existed vs created
2. **CLI Research Matrix** - Filled in with real values
3. **Provider Research** - Ollama/LMStudio API details
4. **Unknowns** - What we couldn't determine (needs manual testing)
5. **Prompt Updates** - Summary of changes made to 013-017
</output>
