# Create Prompt: Next-Step Scenarios

> Reference for `commands/create-prompt.md`, moved verbatim so the main body stays under Antigravity's 24000-byte skill limit. Read it after saving prompts, before presenting the decision tree.

<single_prompt_scenario>
If you created ONE prompt (e.g., `./prompts/005-implement-feature.md`):

<presentation>
Saved prompt to ./prompts/005-implement-feature.md

What's next?

If `DEFAULT_RUN_OPTS` is set:
1. Run with your defaults ({DEFAULT_RUN_OPTS})
2. Run prompt now
3. Review/edit prompt first
4. Save for later
5. Other

Choose (1-5): _

If `DEFAULT_RUN_OPTS` is not set:
1. Run prompt now
2. Review/edit prompt first
3. Save for later
4. Other

Choose (1-4): _
</presentation>

<action>
If user chooses "Run with your defaults", append `DEFAULT_RUN_OPTS` verbatim to `/daplug:run-prompt 005` and execute it.

If user chooses "Run prompt now", run `npx cclimits --json 2>/dev/null`, summarize current quota status, then present this model menu:

<!-- BEGIN GENERATED: create-prompt-selection-menu -->
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
  50. agy - {X}% used - 3.8-flash High, default agy shorthand

  **Z.AI / OpenCode:** {usage status}
  51. zai - {X}% used - Z.AI GLM-4.7
  52. glm5 - {X}% used - Z.AI GLM-5.3 latest alias
  53. glm52 - {X}% used - Z.AI GLM-5.2 explicit pin
  54. glm53 - {X}% used - Z.AI GLM-5.3 explicit pin
  55. flash - {X}% used - Z.AI GLM-5.3-Flash multimodal, 3x quota, reasoning max
  56. glm53-flash - {X}% used - Z.AI GLM-5.3-Flash versioned alias of flash
  57. kimi - {X}% used - Kimi K2.5 via OpenCode
  58. opencode - {X}% used - OpenCode GLM-4.7

  **Synthetic:** {usage status}
  59. synthetic - {requests}/{limit} requests - Synthetic floating (currently DS V4.1 Flash)
  60. syn-flash - {requests}/{limit} requests - Synthetic floating (currently GLM-4.7-Flash)
  61. syn-kimi - {requests}/{limit} requests - Synthetic floating (currently Kimi-K3) vision
  62. syn-kimi3 - {requests}/{limit} requests - Synthetic Kimi-K3 vision
  63. syn-qwen - {requests}/{limit} requests - Synthetic floating (currently Qwen3.8-27B) vision
  64. syn-minimax - {requests}/{limit} requests - Synthetic MiniMax-M3 vision
  65. syn-nemotron - {requests}/{limit} requests - Synthetic Nemotron-3-Super
  66. syn-glm53 - {requests}/{limit} requests - Synthetic GLM-5.3 beta text-only
  67. syn-glm53-flash - {requests}/{limit} requests - Synthetic GLM-5.3-Flash beta vision
  68. syn-ds41-flash - {requests}/{limit} requests - Synthetic DeepSeek V4.1 Flash vision
  69. deepseek - {requests}/{limit} requests - Synthetic DeepSeek V4.1 Flash (alias of syn-ds41-flash)

  **Local:** {usage status}
  70. local - local qwen3.6-35b-a3b, no quota
  71. qwen - local qwen3.6-35b-a3b, no quota
  72. devstral - local Devstral, no quota
  73. glm-local - local GLM-4.7 Flash, no quota
  74. qwen-small - local qwen3-4b, no quota
  75. qwen36 - local qwen3.6-35b-a3b, no quota
  76. qwen36-27b - local qwen3.6-27b, no quota

  Choose (1-76), or type model with flags (e.g., 'codex --worktree --loop'): _
<!-- END GENERATED: create-prompt-selection-menu -->

After selection:
- If the user typed model flags, append those flags to `/daplug:run-prompt 005`.
- If the user selected a listed model, run `/daplug:run-prompt 005 --model {selected_model}`.
- If the selected model is `claude`, `--model claude` may be omitted, but keeping it is valid.
- Add `--worktree`, `--loop`, or other flags if the user requested them.
- If the user chose to set defaults, save the exact selected flags string with `python3 "$CONFIG_READER" set default_run_prompt_options "$SELECTED_FLAGS" --scope user` before executing.
</action>
</single_prompt_scenario>

<parallel_scenario>
If you created MULTIPLE prompts that CAN run in parallel (e.g., independent modules, no shared files):

<presentation>
Saved prompts:
- ./prompts/005-implement-auth.md
- ./prompts/006-implement-api.md
- ./prompts/007-implement-ui.md

What's next?

If `DEFAULT_RUN_OPTS` is set:
1. Run all prompts in parallel with your defaults ({DEFAULT_RUN_OPTS})
2. Run all prompts in parallel now
3. Run prompts sequentially instead
4. Review/edit prompts first
5. Save for later

Choose (1-5): _

If `DEFAULT_RUN_OPTS` is not set:
1. Run all prompts in parallel now
2. Run prompts sequentially instead
3. Review/edit prompts first
4. Save for later

Choose (1-4): _
</presentation>

<actions>
If running now, run `npx cclimits --json 2>/dev/null`, summarize current quota status, then present this model menu:

<!-- BEGIN GENERATED: create-prompt-parallel-selection-menu -->
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
  50. agy - {X}% used - 3.8-flash High, default agy shorthand

  **Z.AI / OpenCode:** {usage status}
  51. zai - {X}% used - Z.AI GLM-4.7
  52. glm5 - {X}% used - Z.AI GLM-5.3 latest alias
  53. glm52 - {X}% used - Z.AI GLM-5.2 explicit pin
  54. glm53 - {X}% used - Z.AI GLM-5.3 explicit pin
  55. flash - {X}% used - Z.AI GLM-5.3-Flash multimodal, 3x quota, reasoning max
  56. glm53-flash - {X}% used - Z.AI GLM-5.3-Flash versioned alias of flash
  57. kimi - {X}% used - Kimi K2.5 via OpenCode
  58. opencode - {X}% used - OpenCode GLM-4.7

  **Synthetic:** {usage status}
  59. synthetic - {requests}/{limit} requests - Synthetic floating (currently DS V4.1 Flash)
  60. syn-flash - {requests}/{limit} requests - Synthetic floating (currently GLM-4.7-Flash)
  61. syn-kimi - {requests}/{limit} requests - Synthetic floating (currently Kimi-K3) vision
  62. syn-kimi3 - {requests}/{limit} requests - Synthetic Kimi-K3 vision
  63. syn-qwen - {requests}/{limit} requests - Synthetic floating (currently Qwen3.8-27B) vision
  64. syn-minimax - {requests}/{limit} requests - Synthetic MiniMax-M3 vision
  65. syn-nemotron - {requests}/{limit} requests - Synthetic Nemotron-3-Super
  66. syn-glm53 - {requests}/{limit} requests - Synthetic GLM-5.3 beta text-only
  67. syn-glm53-flash - {requests}/{limit} requests - Synthetic GLM-5.3-Flash beta vision
  68. syn-ds41-flash - {requests}/{limit} requests - Synthetic DeepSeek V4.1 Flash vision
  69. deepseek - {requests}/{limit} requests - Synthetic DeepSeek V4.1 Flash (alias of syn-ds41-flash)

  **Local:** {usage status}
  70. local - local qwen3.6-35b-a3b, no quota
  71. qwen - local qwen3.6-35b-a3b, no quota
  72. devstral - local Devstral, no quota
  73. glm-local - local GLM-4.7 Flash, no quota
  74. qwen-small - local qwen3-4b, no quota
  75. qwen36 - local qwen3.6-35b-a3b, no quota
  76. qwen36-27b - local qwen3.6-27b, no quota

  Choose (1-76), or type model with flags (e.g., 'codex --worktree --loop'): _
<!-- END GENERATED: create-prompt-parallel-selection-menu -->

After selection:
- For parallel execution, run `/daplug:run-prompt 005 006 007 --model {selected_model} --parallel`.
- For sequential execution, run `/daplug:run-prompt 005 006 007 --model {selected_model} --sequential`.
- If the selected model is `claude`, `--model claude` may be omitted, but keeping it is valid.
- Add `--worktree`, `--loop`, or other flags if the user requested them.
- If the user typed model flags, append those flags instead of reconstructing them.
- If setting defaults, save the exact selected flags string with `python3 "$CONFIG_READER" set default_run_prompt_options "$SELECTED_FLAGS" --scope user` before executing.
</actions>
</parallel_scenario>

<sequential_scenario>
If you created MULTIPLE prompts that should run sequentially (dependent tasks):

<presentation>
Saved prompts:
- ./prompts/005-setup-foundation.md
- ./prompts/006-build-feature.md
- ./prompts/007-add-tests.md

What's next?

If `DEFAULT_RUN_OPTS` is set:
1. Run all prompts sequentially with your defaults ({DEFAULT_RUN_OPTS})
2. Run all prompts sequentially now
3. Run first prompt only
4. Review/edit prompts first
5. Save for later

Choose (1-5): _

If `DEFAULT_RUN_OPTS` is not set:
1. Run all prompts sequentially now
2. Run first prompt only
3. Review/edit prompts first
4. Save for later

Choose (1-4): _
</presentation>

<actions>
If running now, run `npx cclimits --json 2>/dev/null`, summarize current quota status, then present this model menu:

<!-- BEGIN GENERATED: create-prompt-sequential-selection-menu -->
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
  50. agy - {X}% used - 3.8-flash High, default agy shorthand

  **Z.AI / OpenCode:** {usage status}
  51. zai - {X}% used - Z.AI GLM-4.7
  52. glm5 - {X}% used - Z.AI GLM-5.3 latest alias
  53. glm52 - {X}% used - Z.AI GLM-5.2 explicit pin
  54. glm53 - {X}% used - Z.AI GLM-5.3 explicit pin
  55. flash - {X}% used - Z.AI GLM-5.3-Flash multimodal, 3x quota, reasoning max
  56. glm53-flash - {X}% used - Z.AI GLM-5.3-Flash versioned alias of flash
  57. kimi - {X}% used - Kimi K2.5 via OpenCode
  58. opencode - {X}% used - OpenCode GLM-4.7

  **Synthetic:** {usage status}
  59. synthetic - {requests}/{limit} requests - Synthetic floating (currently DS V4.1 Flash)
  60. syn-flash - {requests}/{limit} requests - Synthetic floating (currently GLM-4.7-Flash)
  61. syn-kimi - {requests}/{limit} requests - Synthetic floating (currently Kimi-K3) vision
  62. syn-kimi3 - {requests}/{limit} requests - Synthetic Kimi-K3 vision
  63. syn-qwen - {requests}/{limit} requests - Synthetic floating (currently Qwen3.8-27B) vision
  64. syn-minimax - {requests}/{limit} requests - Synthetic MiniMax-M3 vision
  65. syn-nemotron - {requests}/{limit} requests - Synthetic Nemotron-3-Super
  66. syn-glm53 - {requests}/{limit} requests - Synthetic GLM-5.3 beta text-only
  67. syn-glm53-flash - {requests}/{limit} requests - Synthetic GLM-5.3-Flash beta vision
  68. syn-ds41-flash - {requests}/{limit} requests - Synthetic DeepSeek V4.1 Flash vision
  69. deepseek - {requests}/{limit} requests - Synthetic DeepSeek V4.1 Flash (alias of syn-ds41-flash)

  **Local:** {usage status}
  70. local - local qwen3.6-35b-a3b, no quota
  71. qwen - local qwen3.6-35b-a3b, no quota
  72. devstral - local Devstral, no quota
  73. glm-local - local GLM-4.7 Flash, no quota
  74. qwen-small - local qwen3-4b, no quota
  75. qwen36 - local qwen3.6-35b-a3b, no quota
  76. qwen36-27b - local qwen3.6-27b, no quota

  Choose (1-76), or type model with flags (e.g., 'codex --worktree --loop'): _
<!-- END GENERATED: create-prompt-sequential-selection-menu -->

After selection:
- For all prompts, run `/daplug:run-prompt 005 006 007 --model {selected_model} --sequential`.
- For the first prompt only, run `/daplug:run-prompt 005 --model {selected_model}`.
- If the selected model is `claude`, `--model claude` may be omitted, but keeping it is valid.
- Add `--worktree`, `--loop`, or other flags if the user requested them.
- If the user typed model flags, append those flags instead of reconstructing them.
</actions>
</sequential_scenario>
