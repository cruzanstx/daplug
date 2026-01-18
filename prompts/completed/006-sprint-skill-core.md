<objective>
Implement the core `/sprint` skill for daplug that automates sprint planning by analyzing technical specifications and generating executable prompts with dependency analysis and model assignment.

This feature transforms a manual 30-60 minute planning process into an automated workflow. It emerged from real usage planning SCP: Black Protocol (13 prompts, 7 phases, 3 models).
</objective>

<context>
Review existing daplug structure:
@skills/prompt-executor/SKILL.md - Pattern for skill definition
@skills/prompt-executor/scripts/executor.py - Pattern for main script
@skills/config-reader/scripts/config.py - Config reading pattern
@commands/run-prompt.md - Command that this will integrate with

Full specification: @daplug_sprint_suggestion.md
</context>

<requirements>
Create the sprint skill with this structure:

```
skills/sprint/
├── SKILL.md              # Skill definition with tool permissions
└── scripts/
    └── sprint.py         # Main implementation
```

### SKILL.md Requirements
- Define skill metadata (name: sprint, description)
- Declare tool permissions: Read, Write, Bash, Glob, Grep
- Document all CLI arguments and options
- Include usage examples

### sprint.py Core Functionality

**Phase 1: Spec Analysis**
```python
def analyze_spec(spec_content: str) -> dict:
    """
    Parse technical specification and identify:
    - Core systems (foundation components)
    - Independent modules (can parallelize)
    - Dependent features (require other modules)
    - Integration points (need multiple systems)
    
    Returns structured analysis with components and relationships.
    """
```

**Phase 2: Prompt Generation**
```python
def generate_prompts(analysis: dict, output_dir: str) -> list[str]:
    """
    For each identified component, generate a prompt file with:
    - Context (extracted from spec)
    - Objective (clear deliverable)
    - Requirements (code patterns, interfaces)
    - Acceptance Criteria (checkboxes)
    - Verification (test commands for --loop)
    
    Use prompt-manager to create files with proper numbering.
    Returns list of created prompt paths.
    """
```

**Phase 3: Dependency Analysis**
```python
def build_dependency_graph(prompts: list, analysis: dict) -> dict:
    """
    Build dependency graph by analyzing:
    - Import/reference patterns in requirements
    - Explicit "depends on" statements
    - Implicit ordering (auth before protected routes)
    - Integration requirements
    
    Output ASCII graph and machine-readable structure.
    """
```

**Phase 4: Model Assignment**
```python
def assign_models(prompts: list, available_models: list) -> dict:
    """
    Assign models based on task characteristics:
    
    | Task Type              | Model   | Rationale           |
    |------------------------|---------|---------------------|
    | Architecture/Design    | claude  | Nuanced decisions   |
    | Complex State Machines | claude  | Multi-step logic    |
    | Standard CRUD          | codex   | Pattern matching    |
    | UI/Forms               | codex   | Boilerplate heavy   |
    | API Integration        | gemini  | Documentation heavy |
    | Tests                  | codex   | Repetitive patterns |
    | Data Structures        | codex   | Well-defined patterns|
    
    Check cclimits for availability before assignment.
    """
```

**Phase 5: Execution Plan Generation**
```python
def generate_execution_plan(
    prompts: list,
    dependencies: dict,
    model_assignments: dict,
    options: dict
) -> str:
    """
    Group prompts into phases based on dependencies:
    - Phase 1: No dependencies (can run first)
    - Phase N: Dependencies satisfied by previous phases
    - Within phases: Identify parallel opportunities
    
    Generate:
    1. sprint-plan.md - Human-readable plan
    2. run-sprint.sh - Executable script
    
    Include --worktree and --loop flags based on options.
    """
```

### CLI Interface
```bash
python3 sprint.py <spec-file-or-text> [options]

Options:
  --output-dir DIR      Where to save prompts (default: ./prompts/)
  --plan-file FILE      Where to save plan (default: ./sprint-plan.md)
  --dry-run             Generate plan without creating files
  --models LIST         Available models (default: claude,codex,gemini)
  --max-parallel N      Max concurrent prompts (default: 5)
  --worktree            Use worktree isolation for all prompts
  --loop                Use verification loops for all prompts
  --json                Output results as JSON
```

### Integration Points
- Import and use prompt-manager for prompt creation
- Import and use config-reader for reading daplug settings
- Check cclimits output for model availability
- Generate commands compatible with /run-prompt
</requirements>

<implementation>
Follow these patterns from existing skills:

1. **Argument parsing**: Use argparse like executor.py
2. **JSON output**: Support --json flag for machine-readable output
3. **Error handling**: Graceful failures with clear messages
4. **Logging**: Use print statements for progress, stderr for errors

For spec parsing, use heuristics:
- Look for markdown headers as component boundaries
- Identify keywords: "depends on", "requires", "uses", "after"
- Recognize common patterns: "database", "auth", "API", "UI", "tests"
- Use sentence structure to infer relationships

For dependency inference:
- Explicit: Text contains "requires X" or "depends on X"
- Implicit: Mentions types/functions from other components
- Structural: Database → Models → Services → Controllers → UI

Model selection should be configurable but have sensible defaults based on task complexity keywords.
</implementation>

<output>
Create these files:

`./skills/sprint/SKILL.md`:
- Skill definition following existing patterns
- Tool permissions declaration
- Full CLI documentation
- Usage examples

`./skills/sprint/scripts/sprint.py`:
- Complete implementation of all 5 phases
- CLI argument handling
- Integration with prompt-manager and config-reader
- Proper error handling and progress output
</output>

<verification>
**Functional Tests:**
```bash
# Test spec analysis (dry run)
cd /storage/projects/docker/daplug
python3 skills/sprint/scripts/sprint.py "Build a REST API with auth and CRUD" --dry-run

# Test with a spec file
echo "# Todo App Spec
## Database
PostgreSQL with users and todos tables.

## Auth
JWT-based authentication. Depends on database.

## API
CRUD endpoints for todos. Requires auth.

## Frontend
React UI. Requires API." > /tmp/test-spec.md

python3 skills/sprint/scripts/sprint.py /tmp/test-spec.md --dry-run --json
```

**Verify outputs:**
- [ ] Spec analysis identifies 4 components
- [ ] Dependency graph shows: Database → Auth → API → Frontend
- [ ] Model assignments are reasonable (claude for auth, codex for CRUD)
- [ ] Execution plan has correct phase ordering
- [ ] Generated commands use /run-prompt syntax correctly

**Unit Tests** (create in skills/sprint/tests/):
```bash
cd skills/sprint && python3 -m pytest tests/ -v
```

Create tests for:
- [ ] Spec parsing with various formats (markdown, bullet points, inline text)
- [ ] Dependency detection (explicit and implicit)
- [ ] Model assignment heuristics
- [ ] Phase grouping algorithm
- [ ] Edge cases: empty spec, single component, circular dependencies
</verification>

<success_criteria>
- [ ] SKILL.md follows existing skill patterns
- [ ] sprint.py implements all 5 phases
- [ ] --dry-run shows plan without creating files
- [ ] --json outputs machine-readable results
- [ ] Dependency graph correctly orders components
- [ ] Model assignments follow the heuristics table
- [ ] Generated /run-prompt commands are valid
- [ ] Unit tests pass
</success_criteria>