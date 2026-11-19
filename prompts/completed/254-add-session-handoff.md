<objective>
Implement a provider-neutral Daplug handoff workflow that lets a user end a long coding-agent session with a compact, evidence-backed checkpoint and resume it safely in a fresh session without replaying the full transcript.

Add user-facing `/daplug:handoff` and `/daplug:resume-handoff` commands backed by one reusable skill and tested Python helpers. The transcript remains a last-resort reference, not the primary context mechanism.
</objective>

<context>
Project: daplug, a Claude Code plugin for multi-model prompt execution.

Read `CLAUDE.md`, then inspect existing command, skill, script, and test patterns before designing the implementation. Relevant existing behavior:

- `commands/create-prompt.md` and `skills/prompt-manager/` can append a Claude session transcript path to prompts.
- Full transcripts are expensive to reload after provider cache expiry and can contain irrelevant history.
- Commands must resolve plugin files through the installed-plugin manifest because `${CLAUDE_PLUGIN_ROOT}` is unreliable in command markdown.
- Daplug supports Claude, Codex, OpenCode, Antigravity/Gemini, Synthetic, and local models; the handoff artifact must not depend on one provider's private session format.
- The working tree may contain unrelated changes. Preserve them and limit edits to this feature.
</context>

<requirements>
1. Add a `handoff` skill containing the format contract and Python helper(s), following existing Daplug skill structure and test conventions.

2. Add `/daplug:handoff` with a small, clear argument surface. It must:
   - Resolve the current Git repository/worktree and capture factual state from Git rather than asking the model to invent it.
   - Create a compact Markdown checkpoint with a versioned machine-readable metadata header and these bounded sections: objective, completed work, decisions and rationale, constraints, changed files, verification evidence, blockers/unresolved questions, and exact next action.
   - Record repository identity, worktree path, branch or detached state, HEAD SHA, dirty-state summary, generation time, and the current transcript path when detectable.
   - Treat the transcript as fallback only and explicitly tell the next agent not to read it unless a specific missing detail requires it.
   - Never claim a test or command passed unless the handoff contains actual evidence supplied or discovered during the current session. Use explicit `not run`/`unknown` states otherwise.
   - Default to a local, untracked Daplug-owned storage location that does not pollute `git status` or require editing the repository's tracked `.gitignore`. Work correctly from linked worktrees and print the exact saved path.
   - Enforce a documented size budget so the handoff stays materially smaller than a transcript. Fail or require compaction rather than silently truncating essential sections.

3. Add `/daplug:resume-handoff [path|latest]`. It must:
   - Resolve an explicit checkpoint or the newest checkpoint for the current repository/worktree.
   - Validate schema/version and repository identity.
   - Compare recorded branch, HEAD, worktree, and dirty-state information with current Git state and clearly distinguish safe matches from drift warnings.
   - Load the compact handoff as working context and present the exact next action, but never automatically edit files, switch/reset branches, restore changes, run commands, or read the full transcript.
   - Gracefully report missing, malformed, oversized, wrong-repository, and unsupported-version artifacts.

4. Keep the artifact provider-neutral and safe:
   - Do not store environment values, credentials, tokens, complete diffs, or arbitrary command output by default.
   - Add conservative secret redaction for handoff text and tests proving common credential forms are removed without exposing fixtures that resemble real credentials.
   - Normalize paths without assuming only one home directory or repository layout.
   - Use atomic writes and restrictive file permissions where supported.

5. Integrate the feature with existing Daplug documentation only where users discover commands/skills. Do not redesign prompt execution, automatic model routing, session management, or transcript discovery beyond the minimum reusable call needed by this feature.
</requirements>

<design_constraints>
- Keep orchestration in command Markdown and deterministic filesystem/Git/schema behavior in Python.
- Prefer one canonical schema/template shared by create and resume paths.
- Do not make a raw transcript summary the artifact; the handoff must be structured and bounded.
- Do not silently modify global Claude settings, project instructions, tracked ignore files, branches, commits, or worktrees.
- Do not add provider-specific resume APIs. Fresh-session startup remains a user action.
- Preserve backward compatibility with existing prompt-manager transcript references.
</design_constraints>

<verification>
Add focused tests covering at minimum:

1. Artifact creation, schema round-trip, atomic replacement behavior, permissions, and deterministic repository identity.
2. Normal repository, detached HEAD, dirty tree, linked worktree, missing Git repository, and paths containing spaces.
3. Latest-artifact selection that cannot cross repository identities accidentally.
4. Exact-match resume plus branch/HEAD/worktree/dirty-state drift warnings.
5. Missing, malformed, unsupported-version, oversized, and wrong-repository artifacts.
6. Size-budget enforcement and secret redaction.
7. Command Markdown references valid skill/script paths and follows installed-plugin path resolution conventions.

Run the new focused tests and the existing affected suites. Run repository-wide checks that are practical for this plugin. Report exact commands and outcomes.
</verification>

<success_criteria>
- [ ] `/daplug:handoff` creates a concise, structured, provider-neutral checkpoint outside tracked repository state and prints its path.
- [ ] `/daplug:resume-handoff` loads the correct checkpoint, validates it, and warns accurately about state drift without mutating the repository.
- [ ] Full transcripts are referenced only as an explicit fallback and are never loaded automatically.
- [ ] Sensitive values and unbounded outputs are excluded or redacted.
- [ ] Linked worktrees and multiple repositories cannot consume each other's `latest` handoff.
- [ ] Focused and affected existing tests pass with exact evidence.
- [ ] Unrelated working-tree changes remain untouched.

When every criterion is satisfied, end with `<verification>VERIFICATION_COMPLETE</verification>`. Otherwise end with `<verification>NEEDS_RETRY: concise reason</verification>`.
</success_criteria>

---
**Session Context**: For full conversation context, see: `/root/.claude/projects/-storage-projects-docker-daplug/cf59325d-3a39-4916-920d-21e875bad8f6.jsonl`