# Create Prompt: Prompt Patterns

> Reference for `commands/create-prompt.md`, moved verbatim so the main body stays under Antigravity's 24000-byte skill limit. Read it while drafting the prompt body in Step 3.

## Prompt Patterns

### For Coding Tasks

```xml
<objective>
[Clear statement of what needs to be built/fixed/refactored]
Explain the end goal and why this matters.
</objective>

<context>
[Project type, tech stack, relevant constraints]
[Who will use this, what it's for]
@[relevant files to examine]
</context>

<requirements>
[Specific functional requirements]
[Performance or quality requirements]
Be explicit about what Claude should do.
</requirements>

<implementation>
[Any specific approaches or patterns to follow]
[What to avoid and WHY - explain the reasoning behind constraints]
</implementation>

<output>
Create/modify files with relative paths:
- `./path/to/file.ext` - [what this file should contain]
</output>

<verification>
**Unit Tests** (REQUIRED for regression protection):
```bash
[appropriate test command based on language/framework]
# Examples:
# Go: cd path/to/package && go test -v
# Python: pytest tests/test_feature.py -v
# JavaScript: npm test -- feature.test.js
```

Create tests for:
- [ ] [Core functionality 1]
- [ ] [Core functionality 2]
- [ ] [Edge cases: empty input, invalid data, boundary conditions]
- [ ] [Error handling and recovery]

Before declaring complete, verify your work:
- [Specific test or check to perform]
- [How to confirm the solution works]
- [ ] All unit tests pass
</verification>

<success_criteria>
[Clear, measurable criteria for success]
</success_criteria>
```

### For Analysis Tasks

```xml
<objective>
[What needs to be analyzed and why]
[What the analysis will be used for]
</objective>

<data_sources>
@[files or data to analyze]
![relevant commands to gather data]
</data_sources>

<analysis_requirements>
[Specific metrics or patterns to identify]
[Depth of analysis needed - use "thoroughly analyze" for complex tasks]
[Any comparisons or benchmarks]
</analysis_requirements>

<output_format>
[How results should be structured]
Save analysis to: `./analyses/[descriptive-name].md`
</output_format>

<verification>
[How to validate the analysis is complete and accurate]
</verification>
```

### For Research Tasks

```xml
<research_objective>
[What information needs to be gathered]
[Intended use of the research]
For complex research, include: "Thoroughly explore multiple sources and consider various perspectives"
</research_objective>

<scope>
[Boundaries of the research]
[Sources to prioritize or avoid]
[Time period or version constraints]
</scope>

<deliverables>
[Format of research output]
[Level of detail needed]
Save findings to: `./research/[topic].md`
</deliverables>

<evaluation_criteria>
[How to assess quality/relevance of sources]
[Key questions that must be answered]
</evaluation_criteria>

<verification>
Before completing, verify:
- [All key questions are answered]
- [Sources are credible and relevant]
</verification>
```

