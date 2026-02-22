<objective>
Capture our current discussion and produce a concrete implementation plan for adding Claude-style task orchestration to daplug, where small worker agents manage provider-specific execution (opencode, codex, gemini) through a unified task lifecycle.

This plan matters because daplug already has strong execution primitives (routing, worktrees, loop/verification), but it needs a durable control plane for multi-task scheduling, dependency management, and worker coordination.
</objective>

<context>
Read project conventions first:
- @CLAUDE.md
- @README.md

Analyze current implementation points:
- @skills/prompt-executor/scripts/executor.py
- @commands/run-prompt.md
- @commands/prompts.md
- @skills/sprint/scripts/sprint.py
- @skills/prompt-manager/scripts/manager.py

Assume the target audience is maintainers of daplug who will implement this in incremental PRs.
</context>

<requirements>
1. Thoroughly analyze the existing execution architecture before proposing changes.
2. Propose a task orchestration design that introduces:
   - A controller/orchestrator role
   - Provider workers (opencode-worker, codex-worker, gemini-worker)
   - A durable task store/state machine
   - Dependency-aware scheduling (DAG-lite: blocked/unblocked)
   - Retry and failure policy aligned with existing loop semantics
3. Define a concrete task schema (required/optional fields) and status transitions.
4. Define worker contract inputs/outputs so workers can be swapped or extended.
5. Specify concurrency and safety model (locking, atomic writes, crash recovery).
6. Include migration strategy that reuses existing executor.py behavior instead of rewriting it.
7. Include at least 3 implementation phases (MVP -> hardening -> optional advanced features).
8. Include risks, tradeoffs, and explicit out-of-scope items.
</requirements>

<implementation>
Use a practical architecture-first approach:
1. Map the current flow (prompt resolution -> model routing -> execution -> logging/loop state).
2. Identify seams where orchestration can be added with minimal disruption.
3. Consider multiple storage options and justify the recommendation (file-backed JSON + locks vs SQLite WAL).
4. Recommend a minimal starting design and an upgrade path.
5. Explain WHY each major design decision is chosen.

For maximum efficiency, whenever you need multiple independent investigations, invoke relevant tools in parallel.
After receiving tool results, reflect on quality and consistency before finalizing recommendations.
</implementation>

<constraints>
- Do not implement code in this task; produce planning + design artifacts only.
- Keep recommendations compatible with existing CLI UX (`/daplug:run-prompt`, model shorthands, worktree/loop flags).
- Prefer small, reversible steps over large refactors.
- Preserve backward compatibility for existing prompts and executor usage.
</constraints>

<output>
Create these files:
- `./docs/task-orchestration-plan.md` - main design and phased implementation plan
- `./docs/task-orchestration-schema.md` - task/worker/state-machine contract details
- `./docs/task-orchestration-risks.md` - risks, mitigations, and rollout guardrails

In `task-orchestration-plan.md`, include:
- Current-state summary
- Target architecture diagram (textual is fine)
- Phase-by-phase rollout with acceptance criteria
- Integration points with existing daplug scripts/commands
</output>

<verification>
Before completion, verify:
- The plan references actual files/functions in this repository.
- Each phase has explicit entry/exit criteria.
- Task schema includes id, ownership, dependencies, retries, timestamps, and status.
- Failure handling includes timeout, retry backoff, and crash recovery.
- Backward compatibility and migration strategy are explicit.
</verification>

<success_criteria>
- A maintainer can start implementation immediately without major ambiguity.
- The plan is specific enough to split into actionable prompts/PRs.
- The proposed design clearly explains how provider workers (opencode/codex/gemini) are managed by a unified orchestration layer.
</success_criteria>