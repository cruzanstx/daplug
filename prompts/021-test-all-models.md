# Test All Available Models

## Objective
Systematically test all available model shorthands to verify the CLI detection and routing system works end-to-end.

## Test Matrix

Run a simple task with each model to verify:
1. Router resolves the shorthand correctly
2. CLI launches successfully
3. Model responds and completes the task

### Models to Test

| Model | CLI | Expected Behavior |
|-------|-----|-------------------|
| `codex` | codex | GPT-5.2-Codex via OpenAI |
| `codex-high` | codex | GPT-5.2-Codex with high reasoning |
| `gemini` | gemini | Gemini 3 Flash Preview |
| `gemini-high` | gemini | Gemini 2.5 Pro |
| `opencode` | opencode | GLM-4.7 via Z.AI |
| `local` | codex --profile local | Best available LMStudio model |
| `qwen` | codex --profile local | Qwen model from LMStudio |
| `devstral` | codex --profile local-devstral | Devstral from LMStudio |

### Test Task

Each model should complete this simple task:

```
Create a file /tmp/model-test-{MODEL_NAME}.txt containing:
1. The model name
2. Current timestamp
3. A one-sentence description of what makes this model unique

Then read and display the file contents.
```

## Execution Plan

### Phase 1: Quick Models (Fast, API-based)
Run these in parallel (they're fast):
```bash
# Tier 1 - Standard speed
/run-prompt 021 --model codex
/run-prompt 021 --model gemini
/run-prompt 021 --model opencode

# Tier 2 - Higher reasoning (slower)
/run-prompt 021 --model codex-high
/run-prompt 021 --model gemini-high
```

### Phase 2: Local Models (Slower, depends on hardware)
Run sequentially to avoid overloading LMStudio:
```bash
/run-prompt 021 --model local
/run-prompt 021 --model qwen
/run-prompt 021 --model devstral
```

### Phase 3: Premium Models (Use sparingly)
Only if specifically testing high-end capabilities:
```bash
/run-prompt 021 --model codex-xhigh
/run-prompt 021 --model gemini-xhigh
/run-prompt 021 --model gpt52-xhigh
```

## Verification

After all tests complete, verify results:
```bash
ls -la /tmp/model-test-*.txt
cat /tmp/model-test-*.txt
```

## Expected Output

Each test should:
1. ✅ Router resolves model → correct CLI
2. ✅ CLI launches without errors
3. ✅ Model creates the test file
4. ✅ File contains correct content

## Notes

- Skip `claude` - that's the subagent, not an external CLI
- `zai` prefers `opencode` when available, so effectively same as `opencode`
- Local models depend on LMStudio running at configured endpoint
- Gemini models require OAuth (`gemini auth login`) or API key
