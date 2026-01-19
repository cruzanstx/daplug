<objective>
Add a `--from-existing` flag to the `/sprint` command that analyzes existing prompts in `prompts/` and generates an execution plan without creating new prompts.

This enables users to create sprint plans from prompts they have already written, skipping the spec-to-prompt generation phase.
</objective>

<context>
Review the existing sprint implementation:
@skills/sprint/scripts/sprint.py - Current implementation with 5 phases
@skills/sprint/SKILL.md - Skill definition to update
@commands/sprint.md - Command definition to update

The sprint skill currently:
1. Analyzes a spec → identifies components
2. Generates new prompts from the spec
3. Builds dependency graph
4. Assigns models
5. Generates execution plan

With `--from-existing`, we skip steps 1-2 and start from step 3 using existing prompts.
</context>

<requirements>
### CLI Changes

Add new flags to sprint.py:

```bash
python3 sprint.py --from-existing [options]

Options for --from-existing mode:
  --from-existing         Use existing prompts instead of generating new ones
  --prompts <list>        Specific prompts to include (e.g., "001-005,010")
  --folder <path>         Only include prompts from this subfolder
  --exclude <list>        Exclude specific prompts (e.g., "003,007")
```

### Examples

```bash
# Analyze all prompts in prompts/
/sprint --from-existing

# Only specific prompts
/sprint --from-existing --prompts 001-005,010

# Only prompts in a subfolder
/sprint --from-existing --folder providers/

# Exclude certain prompts
/sprint --from-existing --exclude 003,007

# Combine with execution options
/sprint --from-existing --worktree --loop
```

### Implementation

1. **Add argument parsing** in sprint.py:
   ```python
   parser.add_argument("--from-existing", action="store_true",
       help="Analyze existing prompts instead of generating from spec")
   parser.add_argument("--prompts", type=str,
       help="Comma-separated prompt numbers/ranges (e.g., 001-005,010)")
   parser.add_argument("--folder", type=str,
       help="Only include prompts from this subfolder")
   parser.add_argument("--exclude", type=str,
       help="Comma-separated prompts to exclude")
   ```

2. **Add prompt discovery function**:
   ```python
   def discover_existing_prompts(
       prompts_dir: Path,
       include: str | None = None,
       folder: str | None = None,
       exclude: str | None = None
   ) -> list[dict]:
       """
       Find existing prompts based on filters.
       
       Returns list of prompt dicts with:
       - number: prompt number (e.g., "001")
       - name: full filename
       - path: absolute path
       - content: prompt content
       - folder: subfolder (empty string for root)
       """
   ```

3. **Add prompt content analysis**:
   ```python
   def analyze_prompt_content(prompt: dict) -> dict:
       """
       Analyze a prompt file to extract:
       - title/objective (from <objective> tag or first heading)
       - dependencies (from "depends on", "@file" references)
       - task_type (for model assignment)
       - verification_commands (from <verification> section)
       """
   ```

4. **Modify main() to handle --from-existing**:
   ```python
   if args.from_existing:
       # Skip spec analysis and prompt generation
       prompts = discover_existing_prompts(
           prompts_dir,
           include=args.prompts,
           folder=args.folder,
           exclude=args.exclude
       )
       
       # Analyze each prompt for dependencies
       for p in prompts:
           p["analysis"] = analyze_prompt_content(p)
       
       # Continue with existing phases 3-5
       dependencies = build_dependency_graph(prompts, {})
       model_assignments = assign_models(prompts, available_models)
       plan = generate_execution_plan(prompts, dependencies, model_assignments, options)
   ```

5. **Update SKILL.md and commands/sprint.md** with new flag documentation

### Dependency Detection from Existing Prompts

Scan prompt content for:
- Explicit: `depends on 001`, `requires prompt 002`
- File references: `@skills/sprint/` → depends on prompts that create those files
- Keywords: "after X is complete", "once Y is done"
- Section headers: Look for "Dependencies" or "Requires" sections

### Output

Same as regular sprint output:
- Dependency graph (ASCII)
- Model assignments table
- Execution plan with phases
- `sprint-plan.md` file
- `run-sprint.sh` script (if not --dry-run)
</requirements>

<implementation>
Reuse existing functions where possible:
- `build_dependency_graph()` - works with any prompt list
- `assign_models()` - works with any prompt list  
- `generate_execution_plan()` - works with any prompt list

New functions needed:
- `discover_existing_prompts()` - find and filter prompts
- `analyze_prompt_content()` - extract deps and metadata from content
- `parse_prompt_range()` - parse "001-005,010" syntax (may already exist)

Integration:
- The `--from-existing` flag should be mutually exclusive with providing a spec
- If both are provided, show error and usage help
</implementation>

<output>
Modify these files:

`./skills/sprint/scripts/sprint.py`:
- Add --from-existing, --prompts, --folder, --exclude arguments
- Add discover_existing_prompts() function
- Add analyze_prompt_content() function
- Update main() to handle --from-existing flow

`./skills/sprint/SKILL.md`:
- Document new flags in CLI section
- Add examples for --from-existing usage

`./commands/sprint.md`:
- Add --from-existing to supported syntax
- Add examples showing the new mode
</output>

<verification>
**Functional Tests:**
```bash
cd /storage/projects/docker/daplug

# Test with existing prompts (dry run)
python3 skills/sprint/scripts/sprint.py --from-existing --dry-run

# Test with prompt filter
python3 skills/sprint/scripts/sprint.py --from-existing --prompts 006-007 --dry-run

# Test with folder filter
python3 skills/sprint/scripts/sprint.py --from-existing --folder sprint --dry-run

# Test JSON output
python3 skills/sprint/scripts/sprint.py --from-existing --dry-run --json
```

**Verify outputs:**
- [ ] Discovers prompts correctly from prompts/ directory
- [ ] Filters work (--prompts, --folder, --exclude)
- [ ] Dependency detection extracts relationships from prompt content
- [ ] Model assignments are reasonable based on prompt content
- [ ] Execution plan groups prompts into correct phases
- [ ] Error shown when --from-existing used with a spec argument

**Unit Tests** (add to skills/sprint/tests/test_sprint.py):
- [ ] discover_existing_prompts() with various filters
- [ ] analyze_prompt_content() extracts dependencies correctly
- [ ] parse_prompt_range() handles "001-005,010" syntax
- [ ] --from-existing and spec argument mutual exclusion
</verification>

<success_criteria>
- [ ] --from-existing flag works without a spec argument
- [ ] --prompts filter selects specific prompts
- [ ] --folder filter limits to subfolder
- [ ] --exclude filter removes specific prompts
- [ ] Dependencies detected from prompt content
- [ ] Execution plan correctly orders based on dependencies
- [ ] SKILL.md and commands/sprint.md updated with documentation
- [ ] All existing sprint tests still pass
- [ ] New unit tests pass
</success_criteria>