---
name: cli-detector
description: Detect installed AI coding CLIs and local model providers; outputs a cached JSON inventory for routing (/detect-clis).
allowed-tools:
  - Bash(python3:*)
  - Read
---

# CLI Detector

Phase 1: Detect installed Tier 1 coding CLIs (Claude, Codex, Gemini, OpenCode) via an extensible plugin system.

## Usage

Run the `/detect-clis` renderer (tables + optional fixes):

```bash
python3 skills/cli-detector/scripts/detect_clis.py
python3 skills/cli-detector/scripts/detect_clis.py --json
python3 skills/cli-detector/scripts/detect_clis.py --dry-run
python3 skills/cli-detector/scripts/detect_clis.py --reset
python3 skills/cli-detector/scripts/detect_clis.py --fix
```

Run a scan and print JSON:

```bash
python3 skills/cli-detector/scripts/detector.py --scan
```

Verbose scan (progress to stderr, JSON to stdout):

```bash
python3 skills/cli-detector/scripts/detector.py --scan --verbose
```

List plugins:

```bash
python3 skills/cli-detector/scripts/detector.py --list-plugins
```

Check a specific CLI:

```bash
python3 skills/cli-detector/scripts/detector.py --check codex
```
