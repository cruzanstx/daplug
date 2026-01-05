---
name: check-updates
description: Check if daplug plugin has updates available
---

Run this command, then output the result to the user:

```bash
bash -c 'REMOTE=$(jq -r ".\"daplug\".source.url // empty" ~/.claude/plugins/known_marketplaces.json 2>/dev/null) && INSTALLED=$(jq -r ".plugins.\"daplug@cruzanstx-marketplace\"[0].version // empty" ~/.claude/plugins/installed_plugins.json 2>/dev/null) && LATEST=$(git archive --remote="$REMOTE" HEAD plugins/daplug/.claude-plugin/plugin.json 2>/dev/null | tar -xO 2>/dev/null | jq -r ".version // empty") && echo "daplug: v${INSTALLED:-not installed} -> v${LATEST:-unknown}" && test "$INSTALLED" = "$LATEST" && echo "UP_TO_DATE" || echo "NEEDS_UPDATE"'
```

Based on output, respond:
- If "UP_TO_DATE": `daplug v{VERSION} is up to date`
- If "NEEDS_UPDATE":
  ```
  Update available! Run:
    claude plugin uninstall daplug@cruzanstx-marketplace && claude plugin marketplace update daplug && claude plugin install daplug@cruzanstx-marketplace

  Then resume session:
    claude --resume
  ```

Note: You must uninstall first - `claude plugin install` won't overwrite an existing version.
