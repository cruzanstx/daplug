# Product Requirements Document: Plugwalk

## Document Metadata

| Field | Value |
|---|---|
| Product | Plugwalk |
| Repo | `daplug` |
| Status | Draft v1 (implementation-ready) |
| Last Updated | 2026-02-11 |
| Primary Audience | Plugin maintainers, command/skill authors, QA |

## Executive Summary

`plugwalk` is a local observability companion for daplug workflows that makes concurrent work visible in real time.

Today, users can run parallel prompts, background monitors, and loops, but visibility is fragmented across terminal output, log files, and tool status checks. Plugwalk consolidates these signals into one interface with live concurrency lanes, timeline views, and post-run replay.

The v1 product includes:

- A command surface (`/plugwalk`) to start/stop/status/export.
- A local web app to visualize active runs, subagents, loops, retries, and failures.
- A replayable event history backed by local storage.

## Problem Statement

### Current user pain

1. Parallel work is hard to reason about when 2+ jobs run concurrently.
2. Failures are discoverable, but root cause triage is slow due to scattered signals.
3. Loop behavior and subagent lifecycle are not easy to inspect post-hoc.
4. There is no single, low-friction "mission control" view for daplug execution.

### Why now

- Daplug is increasingly orchestration-heavy (`run-prompt`, loops, monitor agents, multi-model runs).
- OpenCode and Claude ecosystems now expose richer events/hooks that can power first-class visualization.
- A read-only observability layer can reduce support/debugging burden immediately, without risky control-plane operations.

## Goals and Non-Goals

### Goals (v1)

1. Show concurrent runs and sub-work in a clear, real-time visualization.
2. Provide fast failure drill-down from timeline event to evidence payload.
3. Preserve local history for replay and postmortem analysis.
4. Keep setup simple: one command, local-only by default.

### Non-Goals (v1)

1. Remote multi-user dashboard.
2. Editing/canceling/retrying jobs from UI.
3. Replacing orchestration logic or becoming a second state authority.
4. Cloud analytics dependencies.

## Target Users

### Primary

- Maintainers and power users running daplug prompts in parallel.
- Developers debugging loop retries, permission blocks, or tool failures.

### Secondary

- Contributors validating behavior before opening PRs.
- Operators reviewing execution patterns and latency hotspots.

## User Jobs-to-be-Done

1. "Show me what is running right now and what is blocked."
2. "Show where this failed and why in under 30 seconds."
3. "Show all child/subagent work attached to this run."
4. "Replay yesterday's run to understand what happened."

## Product Principles

1. **Single source of truth**: consume existing events/logs/hooks; do not invent alternate orchestration state.
2. **Read-only first**: visibility before control actions.
3. **Concurrency first UX**: lanes and timeline are core, not secondary screens.
4. **Evidence over interpretation**: always link summaries to raw payload/log context.
5. **Low overhead**: suitable for always-on local usage.

## Scope

### In Scope (v1)

- `/plugwalk` command (serve/status/stop/replay/export).
- Live dashboard with active run lanes and status chips.
- Timeline view with filters and event detail drawer.
- Run/session drill-down and history replay.
- Local persistence (SQLite or equivalent append-only event store).

### Out of Scope (v1)

- Team sharing, remote auth, or cloud persistence.
- Run mutation controls (cancel/retry/edit prompts).
- Automatic remediation workflows.

## UX and Visual Design Direction

### Theme

"Mission Control Notebook": precise, high-signal, low-gloss.

### Visual language

- Typography:
  - Headings/UI: Space Grotesk
  - Logs/code/payloads: IBM Plex Mono
- Color system:
  - Base: neutral slate/granite tones
  - Status accents: teal (healthy), amber (retry/warn), red (failed), blue (running)
  - Avoid generic purple-heavy default palettes
- Background:
  - Subtle grid and depth gradients to support dense timeline scanning
- Motion:
  - Meaningful only (lane pulse for active work, smooth timeline updates)
  - Respect `prefers-reduced-motion`

### Layout

- Live view: swimlanes per run, nested rows for child sessions/subtasks.
- Timeline view: dense chronological feed with semantic event chips.
- Right-side detail drawer: raw payload + correlated events + artifact links.
- Mobile: stacked cards, sticky filter bar, collapsible detail panel.

## Functional Requirements

### FR-01 Command Lifecycle

- Provide `/plugwalk` command with:
  - `--open`, `--port`, `--source`, `--status`, `--stop`, `--replay`, `--export`
- Print local dashboard URL on startup.

### FR-02 Live Concurrency Board

- Display all active runs with:
  - status, duration, active agent count, iteration info
- Reflect parent/child session relationships.

### FR-03 Timeline and Filtering

- Render event timeline by run/session.
- Support filters by source, agent, severity, status, event type, and time range.

### FR-04 Failure Drill-Down

- Clicking a failed/warn event opens detail view with:
  - summary
  - raw event payload
  - correlated nearby events
  - linked artifacts/log references

### FR-05 Replay

- Support replay from stored event history or imported event JSONL.
- Include timeline scrubber and deterministic ordering.

### FR-06 Export

- Export run-level data as JSON (required) and CSV (optional in v1).

### FR-07 Data Source Adaptation

- Ingest events from:
  - OpenCode event stream and/or plugin JSONL
  - Claude hooks/log-derived lifecycle signals

## Non-Functional Requirements

### Performance

- Live event-to-render latency p95 <= 300 ms.
- Initial load for last 24h data <= 1.5 s on standard dev workstation.

### Reliability

- Service should survive adapter disconnects and resume ingest cleanly.
- Persist offsets/checkpoints to avoid duplicate flood on restart.

### Security and Privacy

- Default bind to `127.0.0.1`.
- Redact obvious secrets (tokens/api keys/cookies) before persistence.
- Avoid arbitrary path reads from UI.

### Accessibility

- Keyboard navigation for major screens and filter/search.
- Color contrast suitable for dense operational dashboards.

## Success Metrics

### Product metrics

1. Time-to-root-cause for run failures reduced by >= 40% vs baseline manual log triage.
2. >= 80% of targeted users report plugwalk as "useful" or "very useful" after first week.
3. >= 70% of parallel run sessions use plugwalk at least once.

### Technical metrics

1. Ingest drop rate < 0.5% under expected local load.
2. Crash-free runtime > 99% during 24h local soak test.

## Risks and Mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| Event schema drift across tool versions | Missing/incorrect visualization | Adapter versioning + defensive parser + unknown-event fallback |
| Too much log noise | Reduced usability | Severity defaults, saved filter views, incident grouping |
| Local resource overhead | Users disable feature | Bounded queue, sampling knobs, retention controls |
| Sensitive data leakage in payloads | Security/privacy issue | Redaction pipeline + export warning gate |

## Release Plan

### Milestone M1: Foundation and Ingestion

- Deliver event schema, adapters, and local persistence.

### Milestone M2: Live Dashboard MVP

- Deliver live lanes, timeline, filters, and event drill-down.

### Milestone M3: Replay and Export

- Deliver replay controls, run history views, and export endpoints.

### Milestone M4: Hardening

- Deliver reliability/performance/security tuning and docs.

## Milestone Tickets (Product-Level)

- `PLGW-001` Finalize PRD scope, goals, and acceptance criteria.
- `PLGW-002` Approve visual direction and dashboard IA.
- `PLGW-003` Define event taxonomy and severity model.
- `PLGW-004` Validate key user journeys with internal dogfood.
- `PLGW-005` Lock v1 go-live checklist and rollout communication.

## Acceptance Criteria (v1 Release)

1. `/plugwalk --open` launches local UI and displays live activity.
2. Two concurrent runs are clearly visible as distinct lanes.
3. Run/session hierarchy appears correctly for child session workflows.
4. Failed events expose raw payload evidence in detail drawer.
5. Replay mode can load and scrub historic events deterministically.
6. Local-only default bind and redaction path are enabled.

## Product Checklist

- [ ] PRD approved by maintainers.
- [ ] v1 scope explicitly locked (no control-plane actions).
- [ ] UX density and theme validated on desktop and mobile.
- [ ] Success metrics instrumentation plan defined.
- [ ] Release notes and user-facing command docs prepared.
