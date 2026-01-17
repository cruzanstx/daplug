---
name: check-updates
description: Check if daplug plugin has updates available
---

Run this command, then output the result to the user:

```bash
INSTALLED=$(jq -r '.plugins."daplug@cruzanstx"[0].version // empty' ~/.claude/plugins/installed_plugins.json 2>/dev/null)
LATEST=$(curl -sf https://raw.githubusercontent.com/cruzanstx/daplug/main/.claude-plugin/plugin.json | jq -r '.version // empty')
echo "daplug: v${INSTALLED:-not installed} -> v${LATEST:-unknown}"
[[ -n "$INSTALLED" && -n "$LATEST" && "$INSTALLED" == "$LATEST" ]] && echo "UP_TO_DATE" || echo "NEEDS_UPDATE"
```

Based on output, respond:
- If "UP_TO_DATE": `daplug v{VERSION} is up to date`
- If "NEEDS_UPDATE":
  ```
  Update available! Run:
    claude plugin uninstall daplug@cruzanstx && claude plugin marketplace update cruzanstx && claude plugin install daplug@cruzanstx

  Then resume session:
    claude --resume
  ```

Note: You must uninstall first - `claude plugin install` won't overwrite an existing version.
