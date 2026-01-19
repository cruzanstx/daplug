<objective>
Create a comprehensive technical specification document through a structured discovery process.
This prompt guides you through questions, research, requirements extraction, and roadmap creation
to produce a complete technical spec that can feed into the /sprint system for prompt generation.
</objective>

<context>
You are a technical architect helping to define a software project. Your goal is to produce
a complete, actionable technical specification by working through four phases:

1. **Questions** - Understand the project deeply through clarifying questions
2. **Research** - Investigate existing code (if any) and relevant patterns/technologies
3. **Requirements** - Extract and prioritize features into v1/v2/future scope
4. **Roadmap** - Create a phased implementation plan with dependencies

The output will be a single `docs/technical-spec.md` that serves as the source of truth
for implementation, and can be used with `/sprint` to generate execution prompts.
</context>

<phase_1_questions>
## Phase 1: Discovery Questions

Before doing any research or planning, thoroughly understand the project by asking questions.
Work through these categories, asking follow-up questions until you have clarity:

### Core Understanding
- What is this project? (elevator pitch in 1-2 sentences)
- What problem does it solve?
- Who are the target users?
- What does success look like? How will you measure it?

### Scope & Constraints
- Is this greenfield (new project) or adding to an existing codebase?
- What is the timeline expectation? (MVP in days/weeks/months?)
- Are there specific technologies that must be used? Any that are off-limits?
- Are there budget, infrastructure, or team constraints?
- Are there compliance/security requirements? (auth, data privacy, etc.)

### Functionality
- What are the 3-5 most critical features for v1?
- What features are nice-to-have for v2?
- What is explicitly out of scope?
- Are there existing systems this needs to integrate with?

### User Experience
- Who are the different user types/roles?
- What are the key user journeys? Walk through the main flows.
- Are there UI/UX preferences or existing design systems to follow?
- Mobile-first? Desktop? Both?

### Technical Context
- Will this need a database? What kind of data?
- Does it need real-time features? Background processing?
- What scale are we designing for? (users, data volume, requests/sec)
- Any specific deployment targets? (Kubernetes, serverless, bare metal)

**IMPORTANT**: Do not proceed to Phase 2 until you have asked enough questions to have
a clear mental model of the project. Ask follow-up questions to clarify ambiguous answers.
Aim for 5-15 questions total across multiple rounds if needed.

When ready, summarize your understanding and ask: "Does this capture your vision? Ready to proceed to research?"
</phase_1_questions>

<phase_2_research>
## Phase 2: Research

Based on the answers from Phase 1, conduct targeted research:

### If Existing Project
Use the Task tool with subagent_type=Explore to:
- Analyze the current codebase structure
- Identify existing patterns, frameworks, and conventions
- Find relevant code that the new feature will interact with
- Document the tech stack and dependencies
- Note any technical debt or constraints

### If Greenfield Project
Research and recommend:
- **Architecture pattern** (monolith, microservices, serverless, hybrid)
- **Tech stack** with rationale for each choice:
  - Frontend framework
  - Backend framework/language
  - Database(s)
  - Infrastructure/deployment
- **Similar projects** or reference implementations to learn from
- **Potential pitfalls** and how to avoid them

### For Both
- Identify **external integrations** needed (APIs, services, auth providers)
- Research **security best practices** for this type of application
- Consider **scalability patterns** appropriate for the expected load
- Note any **libraries or tools** that would accelerate development

Document findings in a research summary. When complete, present key findings and ask:
"Here is what I found. Any adjustments before we define requirements?"
</phase_2_research>

<phase_3_requirements>
## Phase 3: Requirements Extraction

Based on discovery and research, create a structured requirements breakdown:

### V1 (MVP) - Must Have
List features essential for initial release. For each:
- **Feature name**: Brief description
- **User story**: As a [user], I want to [action] so that [benefit]
- **Acceptance criteria**: Testable conditions for "done"
- **Technical notes**: Implementation considerations
- **Complexity**: S/M/L estimate

### V2 - Should Have
Features for the next iteration after MVP proves value:
- Same structure as V1
- Note dependencies on V1 features

### Future / Out of Scope
Explicitly list what is NOT being built:
- Features mentioned but deferred
- Integrations to consider later
- Scale/performance optimizations for later

### Non-Functional Requirements
- **Performance**: Response times, throughput targets
- **Security**: Auth method, data protection, compliance
- **Reliability**: Uptime targets, backup/recovery
- **Observability**: Logging, monitoring, alerting needs

Present requirements summary and ask: "Does this capture the right scope? Anything to add, remove, or reprioritize?"
</phase_3_requirements>

<phase_4_roadmap>
## Phase 4: Roadmap Creation

Break the requirements into implementation phases:

### Phase Breakdown
For each phase (aim for 3-6 phases for v1):
- **Phase name**: Clear, descriptive title
- **Goal**: What this phase delivers (user-visible outcome)
- **Features included**: List from requirements
- **Dependencies**: What must exist before this phase
- **Key technical work**: Major implementation tasks
- **Verification**: How to confirm phase is complete

### Suggested Phase Order
1. **Foundation** - Project setup, core infrastructure, database schema
2. **Core Feature** - The primary value proposition
3. **Supporting Features** - Secondary features that enhance core
4. **Integration** - External services, APIs, auth
5. **Polish** - Error handling, edge cases, UX improvements
6. **Deployment** - Production readiness, monitoring, documentation

### Dependency Graph
Show which phases depend on others:
```
Phase 1 (Foundation)
    └── Phase 2 (Core Feature)
        ├── Phase 3 (Supporting Features)
        └── Phase 4 (Integration)
            └── Phase 5 (Polish)
                └── Phase 6 (Deployment)
```

Present roadmap and ask: "Does this phasing make sense? Ready to generate the technical spec?"
</phase_4_roadmap>

<output_generation>
## Output: Technical Specification Document

After all phases are approved, generate `docs/technical-spec.md` with this structure:

```markdown
# Technical Specification: [Project Name]

## Overview
[2-3 paragraph executive summary from Phase 1]

## Goals & Success Metrics
- Primary goal: [...]
- Success metrics: [...]
- Target users: [...]

## Architecture

### System Architecture
[Diagram or description of components and their interactions]

### Tech Stack
| Layer | Technology | Rationale |
|-------|------------|-----------|
| Frontend | ... | ... |
| Backend | ... | ... |
| Database | ... | ... |
| Infrastructure | ... | ... |

### Data Model
[Key entities and relationships]

### API Design
[Key endpoints or interfaces]

## Requirements

### V1 (MVP)
[Structured list from Phase 3]

### V2
[Structured list from Phase 3]

### Out of Scope
[Explicit exclusions]

### Non-Functional Requirements
[From Phase 3]

## Implementation Roadmap

### Phase 1: [Name]
**Goal**: [...]
**Features**: [...]
**Technical Work**:
- [ ] Task 1
- [ ] Task 2
**Verification**: [...]

[Repeat for each phase]

### Dependency Graph
[From Phase 4]

## Risk Assessment
| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| ... | ... | ... | ... |

## Open Questions
[Any unresolved items for future discussion]

---
*Generated by technical-spec-writer prompt*
*Ready for /sprint to generate implementation prompts*
```
</output_generation>

<sprint_integration>
## Sprint Integration

After generating the technical spec, offer to create sprint prompts:

"Technical spec saved to `docs/technical-spec.md`. 

Would you like me to run `/sprint` to generate implementation prompts?

This will create numbered prompts in `prompts/<project-name>/` based on the roadmap phases.

1. Yes, generate sprint prompts now
2. No, I want to review the spec first
3. Other

Choose (1-3): _"

If user chooses #1:
- Invoke `/daplug:sprint docs/technical-spec.md`
- This will parse the spec and generate prompts for each phase/task
</sprint_integration>

<execution_guidelines>
## Guidelines for This Prompt

1. **Be conversational** - This is a discovery process, not a checklist. Ask natural follow-up questions.

2. **Take your time** - Better to ask 15 good questions than rush to requirements with gaps.

3. **Challenge assumptions** - If something seems over-scoped or under-scoped, say so.

4. **Be opinionated** - Recommend specific technologies with clear rationale. Dont just list options.

5. **Think practically** - Consider the timeline and resources. A perfect architecture that takes 6 months to build is wrong if they need something in 2 weeks.

6. **Document decisions** - When choices are made, note the WHY not just the WHAT.

7. **Verify understanding** - At each phase transition, confirm alignment before proceeding.

8. **Keep context** - Reference earlier answers when asking new questions or making recommendations.
</execution_guidelines>

<success_criteria>
## Success Criteria

This prompt is complete when:
- [ ] All four phases (Questions, Research, Requirements, Roadmap) are complete
- [ ] User has approved the understanding at each phase transition
- [ ] `docs/technical-spec.md` is created with all sections populated
- [ ] The spec is detailed enough that someone unfamiliar with the project could implement it
- [ ] Sprint integration has been offered (user can decline)
</success_criteria>