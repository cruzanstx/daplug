<research_objective>
Research Tier 3 AI coding CLIs to determine which have viable non-interactive CLI entrypoints 
for integration into daplug's agent detection system.

These were mentioned in 012-research-prerequisites but not fully investigated.
</research_objective>

<context>
**Completed:**
- Tier 1 CLIs implemented: Claude Code, Codex, Gemini, OpenCode
- Tier 2 CLIs planned (prompt 017): Goose, Aider, GitHub Copilot CLI

**CLIs to Research:**

| CLI | Notes | Priority |
|-----|-------|----------|
| **Mentat** | AI coding agent, found in initial research | High |
| **Cody** | Sourcegraph's AI assistant | High |
| **Continue** | VS Code/JetBrains AI extension | Medium |
| **Amazon Q** | AWS AI assistant (formerly CodeWhisperer) | Medium |
| **Cursor** | AI-first code editor | Medium |
| **Factory Droid** | Unknown - needs discovery | Low |
| **Crush** | Unknown - needs discovery | Low |
| **GPT Engineer** | AI code generation tool | Low |
| **Sweep** | AI junior dev for PRs | Low |

**Key Questions for Each:**
1. Does it have a standalone CLI (not just IDE extension)?
2. Can it run non-interactively (headless mode)?
3. Where is the config stored?
4. What models/providers does it support?
5. Is it actively maintained?
</context>

<research_tasks>
For EACH CLI, research and document:

## 1. Installation & Detection
- How to install (npm, pip, binary, etc.)
- Executable name(s) to detect
- Version command

## 2. CLI Capabilities
- Does it have a CLI? (not just IDE plugin)
- Non-interactive/headless mode available?
- Command to run a prompt without interaction

## 3. Configuration
- Config file location(s)
- Config format (JSON, YAML, TOML, etc.)
- Environment variables used

## 4. Model Support
- What models/providers supported?
- How to list available models?
- Cross-provider support?

## 5. Viability Assessment
Rate each CLI:
- **Viable**: Has CLI, headless mode, worth adding plugin
- **Partial**: Has CLI but limited headless support
- **Not Viable**: IDE-only or no headless mode
- **Unknown**: Needs more research / unclear docs

## Sources to Check
- GitHub repos (README, docs, CLI help)
- Official documentation sites
- Package registries (npm, PyPI)
- Recent issues/discussions about CLI usage
</research_tasks>

<deliverables>
Create `./docs/tier3-cli-research.md` with:

1. **Summary Table** - All CLIs with viability rating
2. **Detailed Findings** - Section per CLI with research results
3. **Recommendations** - Which to add to daplug, in what order
4. **Plugin Specs** - For viable CLIs, document:
   - `executable_names`
   - `config_paths`
   - `version_cmd`
   - `headless_cmd`
   - `supported_providers`
</deliverables>

<verification>
Before completing, verify:
- [ ] All 9 CLIs researched (even if result is "not viable")
- [ ] Each has clear viability rating with justification
- [ ] Viable CLIs have complete plugin specs
- [ ] Sources cited for key findings
</verification>

<success_criteria>
- Research doc at `./docs/tier3-cli-research.md`
- Clear go/no-go recommendation for each CLI
- Enough detail to implement plugins for viable CLIs
</success_criteria>