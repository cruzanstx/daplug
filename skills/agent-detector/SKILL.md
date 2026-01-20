---
name: agent-detector
description: Detect installed AI coding CLIs and local model providers; outputs a cached JSON inventory for routing (/load-agents).
allowed-tools:
  - Bash(python3:*)
  - Read
---

# Agent Detector

Phase 1: Detect installed Tier 1 coding CLIs (Claude, Codex, Gemini, OpenCode) via an extensible plugin system.

## Usage

Run the `/load-agents` renderer (tables + optional fixes):

```bash
python3 skills/agent-detector/scripts/load_agents.py
python3 skills/agent-detector/scripts/load_agents.py --json
python3 skills/agent-detector/scripts/load_agents.py --reset
python3 skills/agent-detector/scripts/load_agents.py --fix
```

Run a scan and print JSON:

```bash
python3 skills/agent-detector/scripts/detector.py --scan
```

Verbose scan (progress to stderr, JSON to stdout):

```bash
python3 skills/agent-detector/scripts/detector.py --scan --verbose
```

List plugins:

```bash
python3 skills/agent-detector/scripts/detector.py --list-plugins
```

Check a specific CLI:

```bash
python3 skills/agent-detector/scripts/detector.py --check codex
```
