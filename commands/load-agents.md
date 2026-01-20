---
name: load-agents
description: Scan and manage available AI coding agents
argument-hint: "[--fix] [--reset] [--json] [--refresh]"
---

<objective>
Scan for installed AI coding CLIs and local model providers, cache results, and optionally apply safe configuration fixes.
</objective>

<process>

<step1_resolve_paths>
Resolve daplug install paths from Claude's installed plugins manifest:

```bash
PLUGIN_ROOT=$(jq -r '.plugins."daplug@cruzanstx"[0].installPath' ~/.claude/plugins/installed_plugins.json)
DETECTOR="$PLUGIN_ROOT/skills/agent-detector/scripts/detector.py"
FIXER="$PLUGIN_ROOT/skills/agent-detector/scripts/fixer.py"
CACHE=~/.claude/daplug-agents.json
```
</step1_resolve_paths>

<step2_reset_if_requested>
If `--reset` is present, move the cache aside (no data loss) and force a rescan:

```bash
REFRESH_FLAG=""

if [[ "$ARGUMENTS" == *"--reset"* ]]; then
  if [[ -f "$CACHE" ]]; then
    TS=$(date +%Y%m%d-%H%M%S-%N)
    mv "$CACHE" "$CACHE.bak.$TS"
    echo "🗑️ Moved cache to: $CACHE.bak.$TS"
  fi
  REFRESH_FLAG="--refresh"
fi
```
</step2_reset_if_requested>

<step3_fix_if_requested>
If `--fix` is present, apply safe fixes (no secrets):

```bash
if [[ "$ARGUMENTS" == *"--fix"* ]]; then
  echo "🔧 Applying fixes..."
  python3 "$FIXER" --non-interactive
  echo ""
fi
```
</step3_fix_if_requested>

<step4_scan_and_render>
Scan and render output:

**JSON mode** (`--json`):

```bash
if [[ "$ARGUMENTS" == *"--refresh"* ]]; then
  REFRESH_FLAG="--refresh"
fi

if [[ "$ARGUMENTS" == *"--json"* ]]; then
  python3 "$DETECTOR" --scan $REFRESH_FLAG
  exit 0
fi
```

**Human mode** (default):

```bash
if [[ "$ARGUMENTS" == *"--refresh"* ]]; then
  REFRESH_FLAG="--refresh"
fi

python3 "$DETECTOR" --scan $REFRESH_FLAG | python3 - <<'PY'
import json
import sys

data = json.load(sys.stdin)
clis = data.get("clis") or {}
providers = data.get("providers") or {}

installed = [(k, v) for k, v in clis.items() if (v or {}).get("installed")]
missing = [k for k, v in clis.items() if not (v or {}).get("installed")]

print("🔍 Scanning for AI coding agents...\\n")

print(f"✅ Found {len(installed)} installed CLIs:\\n")
print("| CLI | Version | Issues |")
print("|---|---:|---:|")
for name, info in sorted(installed, key=lambda kv: kv[0]):
    issues = info.get("issues") or []
    version = info.get("version") or "-"
    print(f"| `{name}` | `{version}` | `{len(issues)}` |")

if providers:
    print("\\n🖥️ Local Model Providers:\\n")
    print("| Provider | Running | Endpoint | Loaded Models |")
    print("|---|---:|---|---|")
    for name, info in sorted(providers.items(), key=lambda kv: kv[0]):
        running = "yes" if info.get("running") else "no"
        endpoint = info.get("endpoint") or "-"
        loaded = ", ".join(info.get("loaded_models") or []) or "-"
        print(f"| `{name}` | `{running}` | `{endpoint}` | `{loaded}` |")

if missing:
    print("\\n❌ Not installed:\\n")
    for name in sorted(missing):
        print(f"- `{name}`")

print("\\n💾 Cache saved to `~/.claude/daplug-agents.json`")
PY
```
</step4_scan_and_render>

</process>

