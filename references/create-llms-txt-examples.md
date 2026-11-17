# Create llms.txt: Example Interaction Flows

> Reference for `commands/create-llms-txt.md`, moved verbatim so the main body stays under Antigravity's 24000-byte skill limit. Read it when unsure how a full interaction should go.

## Example Interaction Flows

### Example 1: Basic Library

```
User: "/daplug:create-llms-txt axios"
Assistant:
1. Discovers $LLMS_TXT_DIR
2. Reads $LLMS_TXT_DIR/AGENTS.md
3. Asks: "Which category does axios belong to?" → User selects "javascript"
4. Asks: "Does this need a subdirectory?" → User selects "No subdirectory"
5. Asks: "Any advanced deep-dive files needed?" → User says "No, just the base file"
6. Creates $LLMS_TXT_DIR/prompts/061-create-llms-txt-axios.md
7. Presents execution options
8. User selects "codex-xhigh --worktree --loop"
9. Invokes: /daplug:run-prompt 061 --prompt-file "$LLMS_TXT_DIR/prompts/061-create-llms-txt-axios.md" --model codex-xhigh --worktree --loop
```

### Example 2: With Deep-Dive Files

```
User: "/daplug:create-llms-txt gemini-cli"
Assistant:
1. Discovers $LLMS_TXT_DIR
2. Asks category → "tools"
3. Asks subdirectory → "No subdirectory"
4. Proposes deep-dive files:
   - gemini-cli-configuration-advanced.llms-full.txt
   - gemini-cli-tools-advanced.llms-full.txt
   - gemini-cli-troubleshooting-advanced.llms-full.txt
5. User approves files 1 and 3
6. Creates $LLMS_TXT_DIR/prompts/062-create-llms-txt-gemini-cli.md (includes advanced file instructions)
7. Presents execution options
8. User selects "gemini3pro --worktree"
9. Invokes: /daplug:run-prompt 062 --prompt-file "$LLMS_TXT_DIR/prompts/062-create-llms-txt-gemini-cli.md" --model gemini3pro --worktree
```

### Example 3: Library/Ecosystem Subdirectory

```
User: "/daplug:create-llms-txt bubbletea"
Assistant:
1. Discovers $LLMS_TXT_DIR
2. Asks category → "go"
3. Asks subdirectory → "Library/ecosystem subdirectory"
4. Asks subdirectory name → "charmbracelet"
5. Target: $LLMS_TXT_DIR/go/charmbracelet/bubbletea.llms-full.txt
6. Creates $LLMS_TXT_DIR/prompts/063-create-llms-txt-bubbletea.md
7. User runs with codex-xhigh
```

