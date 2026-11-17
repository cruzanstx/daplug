# Run Prompt: Examples

> Reference for `commands/run-prompt.md`, moved verbatim so the main body stays under Antigravity's 24000-byte skill limit. Read it for invocation examples.

## Examples

```
/daplug:run-prompt 123                           # Single prompt with Claude
/daplug:run-prompt 123 --model codex             # With Codex
/daplug:run-prompt 123 --model codex-high        # Codex alias (default high reasoning variant)
/daplug:run-prompt 123 --model codex-spark       # Codex Spark (lower-latency tier)
/daplug:run-prompt 123 --model codex-high --variant none  # Override alias default reasoning
/daplug:run-prompt 123 --model codex --cli opencode --variant high  # Force OpenCode + variant
/daplug:run-prompt 123 --model glm5              # Z.AI GLM-5.2
/daplug:run-prompt 123 --model glm52             # Z.AI GLM-5.2 explicit pin
/daplug:run-prompt 123 --model synthetic         # Synthetic GLM-5.2 (`syn:large:text`)
/daplug:run-prompt 123 --model syn-kimi          # Synthetic Kimi-K2.6 vision alias
/daplug:run-prompt 123 --model codex --worktree  # Codex in isolated worktree
/daplug:run-prompt 123 --model codex --sandbox   # Codex in bubblewrap sandbox (Linux)
/daplug:run-prompt 123 --model codex --sandbox --sandbox-profile strict  # strict isolation
/daplug:run-prompt 123 --model codex --no-sandbox  # explicit opt-out
/daplug:run-prompt 123 --tmux                    # In tmux session
/daplug:run-prompt 123 --worktree --tmux         # Worktree + tmux (full isolation)
/daplug:run-prompt 002-005 --parallel --worktree # Range: 002, 003, 004, 005
/daplug:run-prompt 002,005,010 --parallel        # Comma list: specific prompts
/daplug:run-prompt 002-004,010 --model codex     # Combined range + single
/daplug:run-prompt 123 --model codex --loop      # With verification loop
/daplug:run-prompt 123 --model codex --loop --max-iterations 5  # Custom max
/daplug:run-prompt 123 --model codex --worktree --loop  # Worktree + loop
/daplug:run-prompt 123 --model codex --loop --require-diff  # Verify file changes before accepting completion
/daplug:run-prompt 123 --moa codex,synthetic,qwen36  # Mixture-of-agents: 3 models, 3 worktrees, you judge
/daplug:run-prompt 123 --moa codex,glm5 --loop       # MoA with per-runner verification loops
/daplug:run-prompt 123 --moa codex:opencode,qwen36   # MoA with per-entry CLI override
/daplug:run-prompt 123 --moa codex,codex:opencode    # Same model, two CLIs — compare harnesses
```

