<objective>
Create comprehensive llms-full.txt documentation for the daplug Agent Teams Orchestration system — a meta-orchestration layer that enables Claude Code agent teams to coordinate multi-CLI prompt execution across Claude, OpenCode, Codex, Gemini, and other AI coding CLIs.

This documentation captures the design, architecture, syntax, and usage patterns for two new daplug skills:
1. `/create-at-prompt` — generates agent-team orchestrated prompts with sub-prompts and delegation
2. `/run-at-prompt` — takes existing prompts and runs them with agent team orchestration

This is a NEW feature being designed for the daplug plugin ecosystem. The documentation should serve as both a design specification and a reference guide for implementation.
</objective>

<context>
This documentation belongs in the llms_txt knowledge base at:
`./llms_txt/tools/ai-cli/claude-code/daplug-agent-teams-orchestration.llms-full.txt`

**Background**: The daplug plugin for Claude Code already has:
- `/create-prompt` — creates single-agent prompts
- `/run-prompt` — executes prompts with various AI models (claude, codex, gemini, opencode, zai, local)
- `/sprint` — sequential multi-prompt execution
- Worktree isolation for parallel development
- tmux sessions for background execution
- Verification loops for quality gates

**The Gap**: Currently, there is no way to:
- Create prompts that self-orchestrate across multiple agents/CLIs
- Run a set of existing prompts with intelligent dependency resolution and parallel execution
- Use Claude agent teams as an orchestration layer for multi-CLI workflows

**Related Existing Documentation** (read these for context and cross-referencing):
- `./llms_txt/tools/ai-cli/claude-code/claude-code-agent-teams.llms-full.txt` — Claude Code agent teams reference
- `./llms_txt/tools/ai-cli/claude-code/claude-code-agent-orchestration.llms-full.txt` — Agent orchestration patterns
- `./llms_txt/tools/ai-cli/claude-code/claude-code-task-tool-advanced.llms-full.txt` — Task() API reference

Read the CLAUDE.md and AGENTS.md for repository conventions and documentation standards.
</context>

<research>
Before writing, read these files to understand the existing ecosystem:

1. `./llms_txt/tools/ai-cli/claude-code/claude-code-agent-teams.llms-full.txt` — Understand the Task() API, agent team archetypes, and orchestration patterns
2. `./llms_txt/tools/ai-cli/claude-code/claude-code-agent-orchestration.llms-full.txt` — Agent orchestration patterns
3. `./AGENTS.md` — Documentation quality standards
4. `./CLAUDE.md` — Repository conventions
5. `./DOCUMENTATION-INDEX.md` — Where to register the new file

Also search for any existing OpenCode task orchestration docs in `./llms_txt/tools/ai-cli/opencode/` for cross-referencing the multi-CLI delegation concept.
</research>

<requirements>
The documentation must cover these sections comprehensively:

## 1. Overview & Motivation
- Why agent teams orchestration matters for multi-CLI workflows
- The gap between single-prompt execution and complex multi-agent coordination
- How this builds on existing daplug primitives (worktrees, tmux, loops)

## 2. Architecture
- Meta-orchestration layer: Claude agent teams as the brain, other CLIs as the hands
- The flow: intent → decomposition → delegation → execution → validation → merge
- Diagram showing: User → /create-at-prompt → orchestrator prompt + sub-prompts → /run-at-prompt → parallel CLI execution → validation

## 3. `/create-at-prompt` Skill
- Purpose: Generate orchestrated prompts from a high-level description
- Input: Task description (like /create-prompt but for complex multi-agent work)
- Output: Main orchestrator prompt + N sub-prompts
- Phases:
  - Phase 1: Plan (Claude native — agent team research)
  - Phase 2: Fan-out sub-prompts (delegated to various CLIs)
  - Phase 3: Validate & merge (Claude native — agent team validator)
- How it differs from /create-prompt
- Example input/output

## 4. `/run-at-prompt` Skill
- Purpose: Take existing prompts and run them with agent team orchestration
- Two modes:
  - **Explicit groups** (manual dependency hints): `220,221 -> 222,223 -> 224`
  - **Auto-deps** (AI-driven): `--auto-deps` flag lets orchestrator read prompts and build DAG
- Group syntax: `->` separates sequential phases, `,` separates parallel items within a phase
- Flags: `--validate`, `--model`, `--auto-deps`
- Execution flow:
  1. Parse group syntax OR read all prompts for auto-deps
  2. Build execution DAG
  3. For each phase: fan-out parallel prompts via worktrees + tmux
  4. Wait for phase completion
  5. Optional: validation agent reviews all outputs
  6. Next phase or complete

## 5. Group Syntax Reference
- `220,221 -> 222` — 220 and 221 run in parallel, then 222 runs after both complete
- `220 -> 221,222,223 -> 224` — 220 first, then 221/222/223 in parallel, then 224
- `220,221 -> 222,223 -> 224 --validate` — adds validation phase at the end
- `220 221 222 --auto-deps` — AI reads all prompts and determines execution order
- Hybrid: `220 -> 221,222 --auto-deps -> 224` — some explicit, some auto within groups

## 6. Comparison Table
- `/create-prompt` vs `/create-at-prompt`
- `/run-prompt` vs `/run-at-prompt`
- `/sprint` vs `/run-at-prompt`
- When to use each

## 7. Integration with Existing daplug Infrastructure
- Worktrees: Each parallel sub-prompt gets its own worktree
- tmux: Each execution runs in a named tmux session
- Verification loops: `--loop` flag works per-sub-prompt
- Model routing: Each sub-prompt can target a different CLI/model
- Logging: All executions logged to `~/.claude/cli-logs/`

## 8. Agent Team Roles & Model Tiering

### Model Tiering Strategy
Use the cheapest/fastest model that can handle each role. This is a core architectural principle:

| Role | Model | Rationale |
|------|-------|-----------|
| Monitor agents | **haiku** | Mechanical work: launch commands, watch logs, report status. No reasoning needed. |
| Orchestrator | **sonnet** | Needs to read reports, make decisions, coordinate phases. |
| Planner (auto-deps) | **sonnet** | Reads prompt contents, analyzes dependencies, builds DAG. |
| Validator | **sonnet** | Reviews outputs, checks for conflicts between workstreams. |
| Fixer/Escalation | **opus** | Only spun up when complex failures need deep reasoning. Rare. |
| Merger | **sonnet** | Coordinates git merges, resolves simple conflicts. |

### Monitor Agent (haiku) — The Triage Nurse Pattern
Monitor agents do NOT diagnose — they flag and hand off with the right paperwork. Each monitor:
1. Launches a `/run-prompt` command via tmux
2. Watches the tmux session / log file for completion
3. Produces a structured **Execution Report** with triage flags
4. Hands off to the orchestrator (sonnet) with explicit pointers to what needs attention

### Execution Report Template (haiku output)
```
## Prompt 220 Execution Report
- **Status**: FAIL (exit code 1)
- **Model**: codex-xhigh
- **Duration**: 4m 32s
- **Worktree**: /storage/projects/docker/worktrees/at-220-backend
- **Log**: ~/.claude/cli-logs/codex-xhigh-220-20260212-143200.log
- **tmux session**: at-220-backend (still alive)

### Last 20 lines of output:
[pasted log tail]

### Triage Flags:
- ESCALATE: Test failures detected (3 failing, see log lines 847-892)
- ESCALATE: Merge conflict in src/api/routes.ts (parallel prompt 221 may have touched same file)
- OK: Build succeeded
- OK: Lint clean
```

### Triage Flag Rules (what haiku watches for)
- **Exit code != 0** → always ESCALATE
- **"FAIL" / "error" / "conflict"** in log tail → ESCALATE with line references
- **Duration exceeded threshold** (e.g., 2x expected) → ESCALATE, might be stuck
- **Worktree has uncommitted changes after exit** → ESCALATE, needs merge attention
- **Multiple prompts in same phase touched overlapping files** → ESCALATE to merger agent
- **Clean exit + all checks pass** → OK, ready for next phase

### Orchestrator Decision Flow (sonnet)
When the orchestrator receives haiku reports, it decides:
- All OK → merge worktrees, proceed to next phase
- Test failures → read the log at referenced lines, spin up a fixer agent (opus if complex, sonnet if straightforward)
- File conflicts → send to merger agent with both worktree paths
- Stuck process → kill tmux session, retry with different model or escalate to user

### Agent Roles
- **Planner agent** (sonnet): Decomposes tasks, identifies dependencies, builds execution plans
- **Monitor agents** (haiku): Launch /run-prompt, watch for completion, produce triage reports
- **Validator agent** (sonnet): Reviews outputs, checks for conflicts across workstreams
- **Merger agent** (sonnet): Combines results from parallel branches (git merge coordination)
- **Fixer agent** (opus, on-demand): Handles complex failures that sonnet cannot resolve

## 9. Examples
- Example 1: Simple 2-prompt parallel run with explicit groups
- Example 2: Complex 5-prompt sprint with mixed parallel/sequential
- Example 3: Auto-deps with 4 prompts (AI determines order)
- Example 4: Full /create-at-prompt flow (input → generated prompts → execution)

## 10. Design Decisions & Trade-offs
- Why two separate skills instead of extending existing ones
- Why group syntax uses `->` (pipeline metaphor)
- Why auto-deps is opt-in (predictability vs magic)
- Level 1 (decomposition only) vs Level 2 (self-orchestrating) and when to use each
- Why model tiering (haiku monitors, sonnet orchestrator, opus fixer) — cost optimization without sacrificing quality
- Why the "triage nurse" pattern — monitors don't diagnose, they flag with evidence and let the orchestrator decide
- Why log paths and line numbers are included in handoffs — the orchestrator should never have to search for context
</requirements>

<output>
Create the documentation file at:
`./llms_txt/tools/ai-cli/claude-code/daplug-agent-teams-orchestration.llms-full.txt`

Also update `./DOCUMENTATION-INDEX.md` to register the new file under the appropriate category (likely under "Claude Code / AI CLI Tools" section).

Target length: 800-1200 lines of comprehensive, practical documentation with code examples.
</output>

<verification>
Before declaring complete:
1. Verify the file exists and has proper structure
2. Verify all 10 sections are present with substantive content
3. Verify code examples are complete and realistic
4. Verify DOCUMENTATION-INDEX.md was updated
5. Verify the file follows the naming convention and location standards from AGENTS.md
6. Cross-check against existing agent teams docs to avoid contradiction
</verification>

<success_criteria>
- Documentation is comprehensive enough to serve as both a design spec and implementation guide
- All syntax examples are complete and unambiguous
- The comparison table clearly differentiates when to use each skill
- Examples cover real-world use cases that demonstrate the value
- File is properly registered in DOCUMENTATION-INDEX.md
</success_criteria>