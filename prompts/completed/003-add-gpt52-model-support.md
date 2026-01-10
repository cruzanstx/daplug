<objective>
Add GPT-5.2 (non-codex) model support to daplug for planning and research tasks.

GPT-5.2-Codex is optimized for agentic coding execution, but regular GPT-5.2 excels at deep reasoning, planning, and research. This adds 3 new model options to leverage GPT-5.2's methodical problem-solving capabilities.
</objective>

<context>
daplug currently supports gpt-5.2-codex via shorthand names (codex, codex-high, codex-xhigh).
Research shows GPT-5.2 (non-codex) is better for:
- Complex planning and research tasks
- Ambiguous problems requiring deep reasoning
- Long-running autonomous projects (can work 9+ hours)
- Tasks where thoroughness > speed

Key files:
- `skills/prompt-executor/scripts/executor.py` - Model definitions (~line 478-560)
- `~/.codex/config.toml` - Codex CLI profiles
- `README.md` - Documentation
- `CLAUDE.md` - Model reference table
</context>

<requirements>
## 1. Update executor.py

Add 3 new model entries after the existing codex-xhigh entry (around line 496):

```python
"gpt52": {
    "command": ["codex", "exec", "--full-auto", "-m", "gpt-5.2"],
    "display": "gpt52 (GPT-5.2, planning/research)",
    "env": {},
    "stdin_mode": "dash"
},
"gpt52-high": {
    "command": ["codex", "exec", "--full-auto", "-m", "gpt-5.2", "-c", 'model_reasoning_effort="high"'],
    "display": "gpt52-high (GPT-5.2, high reasoning)",
    "env": {},
    "stdin_mode": "dash"
},
"gpt52-xhigh": {
    "command": ["codex", "exec", "--full-auto", "-m", "gpt-5.2", "-c", 'model_reasoning_effort="xhigh"'],
    "display": "gpt52-xhigh (GPT-5.2, xhigh reasoning, 30+ min tasks)",
    "env": {},
    "stdin_mode": "dash"
},
```

## 2. Update argparse choices

Find the `--model` argument parser (around line 1299-1303) and add the new models to choices:
```python
choices=["claude", "codex", "codex-high", "codex-xhigh", 
         "gpt52", "gpt52-high", "gpt52-xhigh",  # ADD THESE
         "gemini", "gemini-high", ...]
```

## 3. Update ~/.codex/config.toml

Add a profile for gpt-5.2 (optional, for direct CLI use):
```toml
[profiles.gpt52]
model_provider = "openai"
model = "gpt-5.2"
```

## 4. Update README.md

In the "Gemini CLI Model Tiers" section (around line 545-553), add a new section for OpenAI models:

```markdown
### OpenAI Model Tiers

| Shorthand | Model | Best For |
|-----------|-------|----------|
| `codex` | gpt-5.2-codex | Fast coding execution |
| `codex-high` | gpt-5.2-codex (high) | Complex coding |
| `codex-xhigh` | gpt-5.2-codex (xhigh) | Large refactors |
| `gpt52` | gpt-5.2 | Planning, research, analysis |
| `gpt52-high` | gpt-5.2 (high) | Deep reasoning |
| `gpt52-xhigh` | gpt-5.2 (xhigh) | Maximum reasoning (30+ min) |

**When to use GPT-5.2 vs GPT-5.2-Codex:**
- **GPT-5.2-Codex**: Best when plans are clear, need fast execution
- **GPT-5.2**: Best for ambiguous problems, research, methodical analysis
```

## 5. Update CLAUDE.md

Update the "Model Shorthand Reference" table to include the new models.
</requirements>

<verification>
After making changes:

1. Test model resolution:
```bash
PLUGIN_ROOT=$(jq -r '.plugins."daplug@cruzanstx"[0].installPath' ~/.claude/plugins/installed_plugins.json)
python3 "$PLUGIN_ROOT/skills/prompt-executor/scripts/executor.py" --help
# Should show gpt52, gpt52-high, gpt52-xhigh in choices
```

2. Test command generation (dry run):
```bash
python3 "$PLUGIN_ROOT/skills/prompt-executor/scripts/executor.py" 001 --model gpt52
# Should show command with -m gpt-5.2 flag
```

3. Verify README renders correctly (check table formatting)

When all tests pass, output:
<verification>VERIFICATION_COMPLETE</verification>
</verification>

<success_criteria>
- [ ] executor.py has 3 new model entries (gpt52, gpt52-high, gpt52-xhigh)
- [ ] argparse --model choices include new models
- [ ] README.md documents OpenAI model tiers
- [ ] CLAUDE.md model reference table updated
- [ ] ~/.codex/config.toml has gpt52 profile (optional)
</success_criteria>