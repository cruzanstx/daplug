# Create llms.txt: Special Case Templates

> Reference for `commands/create-llms-txt.md`, moved verbatim so the main body stays under Antigravity's 24000-byte skill limit. Read it while writing the prompt file in Step 1.

### Special Case Templates

Include the appropriate special case section based on library type:

**For Go Libraries:**
```xml
<special_case_instructions>
- Include pkg.go.dev documentation
- Cover interfaces, types, methods
- Show testing patterns
- Include module/import paths
</special_case_instructions>
```

**For JavaScript/TypeScript Libraries:**
```xml
<special_case_instructions>
- Include npm package info
- Cover TypeScript types if applicable
- Show both CommonJS and ESM usage
- Include bundler considerations
</special_case_instructions>
```

**For Python Libraries:**
```xml
<special_case_instructions>
- Include PyPI information
- Cover class hierarchies
- Show async patterns if applicable
- Include virtual environment setup
</special_case_instructions>
```

**For CLI Tools:**
```xml
<special_case_instructions>
- Include installation methods (brew, apt, binary)
- Cover all major commands
- Show configuration file formats
- Include shell completion info
</special_case_instructions>
```

**For Frameworks:**
```xml
<special_case_instructions>
- Cover architecture/philosophy
- Include project structure patterns
- Show lifecycle/hooks
- Include plugin/extension systems
</special_case_instructions>
```

