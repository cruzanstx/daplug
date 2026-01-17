<objective>
Fix the verification loop completion marker detection issue where Gemini models fail to output the VERIFICATION_COMPLETE marker even when tasks complete successfully.

This is a cross-model compatibility issue that affects loop mode reliability. The fix must work for ALL supported models (Codex, Gemini, Z.AI, local models) without breaking existing behavior.
</objective>

<context>
**GitHub Issue #2**: Gemini models do not output VERIFICATION_COMPLETE marker in loop mode

**Root Cause**: The current verification protocol in `wrap_prompt_with_verification_protocol()` places the completion marker instruction inside a `<verification_protocol>` XML block. Gemini interprets the entire block as template/example text rather than an action to perform.

**Current problematic code** (lines 1104-1136 in executor.py):
```python
verification_wrapper = f"""<task>
{content}
</task>

<verification_protocol>
## Completion Markers
...
**To signal completion:** Output `<verification>{completion_marker}</verification>` ONLY when:
...
</verification_protocol>
```

**Why Gemini fails**: The marker `<verification>VERIFICATION_COMPLETE</verification>` appears:
1. Inside instructional XML tags (`<verification_protocol>`)
2. In backtick code formatting that looks like template text
3. Nested with other XML-like examples

Codex/Claude models handle this correctly because they recognize the imperative instruction despite the formatting. Gemini treats it as documentation.

**Files to modify**:
- `skills/prompt-executor/scripts/executor.py` - Main fix in `wrap_prompt_with_verification_protocol()`

**Files to reference**:
- `skills/prompt-executor/SKILL.md` - Documentation to update if protocol changes
</context>

<requirements>
1. **Redesign the verification protocol wrapper** to make the completion marker instruction unambiguous across all model types

2. **Suggested approaches** (implement the best one, or combine):
   
   **Option A - Separate MANDATORY section outside XML**:
   Move the completion marker instruction OUTSIDE the `<verification_protocol>` block into a separate, highly visible section at the END of the wrapped prompt:
   ```
   ---
   ## MANDATORY: Completion Signal
   
   After completing ALL tasks and verification, you MUST output this EXACT line:
   
   <verification>VERIFICATION_COMPLETE</verification>
   
   This is a REQUIRED action, not an example. Output it literally when done.
   ---
   ```

   **Option B - Use a simpler, non-XML marker**:
   Change from `<verification>VERIFICATION_COMPLETE</verification>` to a plain text marker:
   ```
   ---VERIFICATION_COMPLETE---
   ```
   This avoids XML confusion entirely. Would require updating:
   - `check_completion_marker()` function
   - `DEFAULT_COMPLETION_MARKER` constant
   - Any regex patterns that look for the XML format

   **Option C - Model-specific protocol wording**:
   Detect if the model is Gemini and use more imperative, repeated instructions:
   ```python
   if model.startswith("gemini"):
       # Add extra emphasis and repeat at end
   ```

3. **Implementation constraints**:
   - Must not break existing Codex/Claude behavior
   - Must work with retry marker `NEEDS_RETRY: [reason]` as well
   - Update `check_completion_marker()` if marker format changes
   - Maintain backward compatibility with existing loop states

4. **Testing approach**:
   - After implementing, the fix can be tested with a simple prompt that just outputs the marker
   - Verify regex patterns still match correctly
</requirements>

<implementation>
**Recommended approach**: Option A (separate MANDATORY section) is the safest and most universal fix.

1. Modify `wrap_prompt_with_verification_protocol()` to:
   - Keep the existing `<verification_protocol>` block for context/explanation
   - Add a new, highly visible MANDATORY section AFTER `</verification_protocol>` and AFTER `</environment>`
   - Use markdown separators (`---`) and strong language ("MANDATORY", "REQUIRED", "MUST")
   - Repeat the exact marker format one more time as a literal action item

2. The new structure should be:
   ```
   <task>
   {content}
   </task>
   
   <verification_protocol>
   ## How Verification Works
   [explanation of the loop system]
   </verification_protocol>
   
   <environment>
   [iteration info]
   </environment>
   
   ---
   ## ⚠️ MANDATORY COMPLETION ACTION
   
   When ALL tasks are complete and verified, you MUST output this EXACT line (not as code, but literally):
   
   <verification>VERIFICATION_COMPLETE</verification>
   
   If tasks are incomplete or failing, output:
   
   <verification>NEEDS_RETRY: [describe what failed]</verification>
   
   This is REQUIRED to signal completion. Do not skip this step.
   ---
   ```

3. Do NOT change the marker format itself (keep `<verification>...</verification>`) to maintain backward compatibility with:
   - Existing `check_completion_marker()` regex
   - Any in-progress loop states
   - User muscle memory
</implementation>

<verification>
After implementing the fix:

1. **Unit test the regex** - Verify `check_completion_marker()` still correctly detects:
   - `<verification>VERIFICATION_COMPLETE</verification>`
   - `<verification>NEEDS_RETRY: some reason</verification>`
   - Does NOT false-positive on the instruction text itself

2. **Test prompt generation** - Run executor in info-only mode and inspect the wrapped content:
   ```bash
   python3 skills/prompt-executor/scripts/executor.py 005 --model gemini --loop
   ```
   Verify the MANDATORY section appears at the end, outside other XML blocks.

3. **Manual integration test** (optional, if time permits):
   - Create a simple test prompt that just says "Output the completion marker"
   - Run with `--model gemini --loop --max-iterations 1`
   - Verify marker is detected

Before declaring complete, verify:
- [ ] `wrap_prompt_with_verification_protocol()` has been updated with the new structure
- [ ] The MANDATORY section appears AFTER `</environment>` in the generated output
- [ ] Existing regex patterns in `check_completion_marker()` still work
- [ ] No changes were made to the marker format (kept `<verification>...</verification>`)

Output: <verification>VERIFICATION_COMPLETE</verification>
</verification>

<success_criteria>
- The verification protocol wrapper now has a separate, highly visible MANDATORY section for the completion marker
- The instruction is placed OUTSIDE all XML blocks to avoid template text confusion
- Both VERIFICATION_COMPLETE and NEEDS_RETRY markers are clearly documented as required actions
- No breaking changes to marker format or regex detection
- The fix is model-agnostic (works for all supported models)
</success_criteria>