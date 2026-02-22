# Technical Specification: Plugwalk

## Document Metadata

| Field | Value |
|---|---|
| Project | Plugwalk |
| Repo | `daplug` |
| Status | Draft v1 (implementation-ready) |
| Last Updated | 2026-02-11 |
| Related | `docs/plugwalk-prd.md` |

## 1. Overview

Plugwalk is a local observability surface for daplug execution. It ingests runtime signals from OpenCode/Claude-compatible sources, normalizes them to a canonical event schema, persists them, and serves a live web UI for concurrent run visualization and replay.

### v1 design constraints

1. Local-only by default (`127.0.0.1`).
2. Read-only observability (no run mutation controls).
3. Adapter-based ingestion with graceful degradation.
4. One canonical event shape regardless of source.

## 2. Architecture

### 2.1 Logical components

1. **Adapters**: source-specific readers that emit canonical events.
2. **Normalizer**: maps source payloads to canonical schema.
3. **Event Bus**: in-process async channel for fan-out.
4. **Storage**: SQLite (WAL) for events/runs/sessions and replay.
5. **API Server**: REST + SSE endpoints for UI and tooling.
6. **Frontend**: SvelteKit dashboard with live lanes + timeline.
7. **CLI Wrapper**: `/plugwalk` command lifecycle manager.

### 2.2 Runtime flow

```text
Source events/logs -> Adapter -> Normalizer -> Event Bus -> (SQLite writer + SSE broadcaster)
                                                          -> REST queries from UI
```

### 2.3 Failure tolerance

- If one adapter fails, others continue.
- Adapter health state is exposed in `/api/v1/health`.
- Backpressure policy uses bounded queue + drop counters + warning events.

## 3. Ingestion Sources and Adapters

### 3.1 Adapter set (v1)

| Adapter | Input | Purpose |
|---|---|---|
| `opencode-sse` | OpenCode event stream | Primary real-time session/message/task events |
| `opencode-jsonl` | plugin JSONL event logs | Replay/offline ingest and fallback |
| `claude-hooks` | hook event payloads | Capture Task/tool/stop lifecycle where configured |
| `cli-log-parser` | `~/.claude/cli-logs/*` | Coarse fallback when richer events unavailable |

### 3.2 Adapter interface

```python
class Adapter(Protocol):
    name: str
    async def start(self, emit: Callable[[CanonicalEvent], Awaitable[None]]) -> None: ...
    async def stop(self) -> None: ...
    async def health(self) -> dict: ...
    async def checkpoint(self) -> dict: ...
```

### 3.3 Checkpointing

- Each adapter stores last processed offset/token timestamp.
- Checkpoint flush interval: 2 seconds (configurable).
- On restart, adapters resume from checkpoint when available.

## 4. Canonical Event Model

### 4.1 Event envelope

```json
{
  "event_id": "evt_01...",
  "ts": "2026-02-11T21:00:00.000Z",
  "source": "opencode|claude|daplug",
  "source_event": "session.status",
  "run_id": "run_...",
  "session_id": "ses_...",
  "parent_session_id": "ses_...|null",
  "agent": "build|explore|validator|unknown",
  "entity_type": "run|session|task|tool|permission|message|todo",
  "entity_id": "id value",
  "status": "queued|running|idle|retry|success|failed|blocked|cancelled",
  "severity": "debug|info|warn|error",
  "title": "Short title",
  "summary": "One-line summary",
  "payload": {},
  "correlation_id": "corr_...",
  "tags": ["loop", "subtask"]
}
```

### 4.2 Event mapping rules

| Source event | Canonical entity/status mapping |
|---|---|
| `session.status` busy | `entity_type=session`, `status=running` |
| `session.status` retry | `entity_type=session`, `status=retry`, `severity=warn` |
| `session.idle` | `entity_type=session`, `status=idle` |
| `permission.updated` | `entity_type=permission`, `status=blocked|running` |
| `message.part.updated` | `entity_type=message`, `status=running` |
| `todo.updated` | `entity_type=todo`, `status=running` |
| Tool failure patterns (log/parser) | `entity_type=tool`, `status=failed`, `severity=error` |

### 4.3 Correlation strategy

- Primary keying: `run_id` + `session_id`.
- Parent/child resolution from explicit source fields; fallback heuristic for parser-only sources.
- `correlation_id` shared across closely related lifecycle events (task start, tool calls, failure, retry).

## 5. Persistence Design

### 5.1 Storage engine

- SQLite with WAL mode.
- Local path default: `~/.claude/plugwalk/plugwalk.db`.
- Retention default: 14 days (configurable).

### 5.2 Schema

```sql
CREATE TABLE runs (
  run_id TEXT PRIMARY KEY,
  source TEXT NOT NULL,
  title TEXT,
  root_session_id TEXT,
  status TEXT NOT NULL,
  started_at TEXT NOT NULL,
  ended_at TEXT,
  metadata_json TEXT
);

CREATE TABLE sessions (
  session_id TEXT PRIMARY KEY,
  run_id TEXT NOT NULL,
  parent_session_id TEXT,
  agent TEXT,
  status TEXT NOT NULL,
  started_at TEXT NOT NULL,
  ended_at TEXT,
  FOREIGN KEY(run_id) REFERENCES runs(run_id)
);

CREATE TABLE events (
  event_id TEXT PRIMARY KEY,
  ts TEXT NOT NULL,
  run_id TEXT,
  session_id TEXT,
  source TEXT NOT NULL,
  source_event TEXT NOT NULL,
  entity_type TEXT NOT NULL,
  entity_id TEXT,
  status TEXT,
  severity TEXT,
  title TEXT,
  summary TEXT,
  payload_json TEXT,
  correlation_id TEXT,
  tags_json TEXT
);

CREATE INDEX idx_events_run_ts ON events(run_id, ts);
CREATE INDEX idx_events_session_ts ON events(session_id, ts);
CREATE INDEX idx_events_source_event_ts ON events(source_event, ts);
CREATE INDEX idx_events_severity_ts ON events(severity, ts);
CREATE INDEX idx_events_correlation ON events(correlation_id);
```

### 5.3 Derived views

- `active_runs_view`: runs where `status in ('running','retry','blocked')`.
- `incident_view`: clustered failed events by `run_id + correlation_id + time window`.

## 6. Backend API

### 6.1 Endpoints (v1)

| Endpoint | Method | Purpose |
|---|---|---|
| `/api/v1/health` | GET | Service + adapter + storage health |
| `/api/v1/runs` | GET | List runs with filters/pagination |
| `/api/v1/runs/{run_id}` | GET | Run summary + aggregates |
| `/api/v1/runs/{run_id}/timeline` | GET | Ordered events for run |
| `/api/v1/sessions/{session_id}/tree` | GET | Parent/child session graph |
| `/api/v1/search` | GET | Event search by text/filters |
| `/api/v1/events/stream` | GET (SSE) | Live event stream |
| `/api/v1/ingest` | POST | Dev-only synthetic ingest |

### 6.2 SSE format

```text
event: plugwalk.event
id: evt_01...
data: {"event_id":"evt_01...","run_id":"run_...",...}

event: plugwalk.heartbeat
data: {"ts":"..."}
```

### 6.3 API response rules

1. JSON everywhere except SSE endpoint.
2. Cursor pagination for `runs` and high-volume searches.
3. UTC timestamps (ISO-8601 with `Z`).

## 7. `/plugwalk` Command Contract

### 7.1 Command behavior

| Command | Behavior |
|---|---|
| `/plugwalk` | Start service with defaults and print URL |
| `/plugwalk --open` | Start service and open browser |
| `/plugwalk --status` | Print daemon status + active adapters |
| `/plugwalk --stop` | Stop daemon gracefully |
| `/plugwalk --replay <path>` | Load replay source and open replay mode |
| `/plugwalk --export <run_id> --format json` | Export run timeline |

### 7.2 Flags

- `--port <int>` default `4517`
- `--source <csv>` default `opencode-sse,claude-hooks`
- `--bind <host>` default `127.0.0.1`

### 7.3 Exit codes

- `0` success
- `2` config/argument error
- `3` adapter startup error
- `4` port bind error

## 8. Frontend Technical Design

### 8.1 Stack

- SvelteKit for app shell/routes.
- Stores for live stream state and filter state.
- Virtualized timeline list for high-volume event rendering.

### 8.2 Main routes

- `/live` active concurrency lanes.
- `/runs` run table and quick status.
- `/timeline` filtered global timeline.
- `/incidents` failure clusters.
- `/settings` adapter and retention controls.

### 8.3 Core UI state

```ts
type UiState = {
  selectedRunId: string | null
  selectedSessionId: string | null
  filters: {
    source: string[]
    agent: string[]
    severity: string[]
    status: string[]
    eventType: string[]
    fromTs?: string
    toTs?: string
  }
  streamConnected: boolean
  replayMode: boolean
}
```

### 8.4 Rendering rules

1. Lanes sorted by most recent activity desc.
2. Child sessions visually nested under parent lane.
3. Event chips use severity + status semantic colors.
4. Detail drawer is source of truth for payload evidence.

## 9. Security and Privacy

### 9.1 Defaults

- Bind to localhost only.
- No auth required on localhost mode.

### 9.2 Redaction pipeline

- Redact common sensitive patterns before persistence:
  - bearer tokens
  - api keys
  - cookie/session tokens
  - obvious secret env vars

### 9.3 Hardening hooks

- Optional `--token` for non-local bind.
- Optional `--allow-export-raw` override for unredacted exports.

## 10. Performance Budgets

| Metric | Target |
|---|---|
| Event ingest throughput | 1,000 events/sec sustained local |
| Event-to-UI latency p95 | <= 300 ms |
| Initial 24h load | <= 1.5 sec |
| Backend memory | <= 300 MB |
| Frontend tab memory | <= 250 MB |

## 11. Test Strategy

### 11.1 Unit tests

- Adapter parsers and mapping logic.
- Correlation and status transition helpers.
- Redaction functions.

### 11.2 Integration tests

- End-to-end ingest -> storage -> SSE path.
- Replay mode ingest from JSONL fixture.
- Multi-run concurrency with parent/child sessions.

### 11.3 UI tests

- Live lane rendering with concurrent fixtures.
- Filter behavior and drill-down drawer integrity.
- Keyboard navigation and reduced-motion behavior.

### 11.4 Acceptance tests

- `/plugwalk --open` launches and streams live events.
- Replay scrubber deterministic for fixture history.

## 12. Rollout Plan and Engineering Milestones

### Phase A: Foundations

Goal: canonical schema, ingest framework, SQLite persistence.

Tickets:
- `PLGW-100` Create canonical event schema + mapper package.
- `PLGW-101` Implement adapter framework and health registry.
- `PLGW-102` Add SQLite storage layer and migrations.
- `PLGW-103` Add baseline unit tests for mapping and storage.

### Phase B: API and Streaming

Goal: operational backend for UI and replay.

Tickets:
- `PLGW-110` Implement `/api/v1/runs*` and session tree endpoints.
- `PLGW-111` Implement SSE broadcaster endpoint.
- `PLGW-112` Add replay ingest API path and cursor pagination.
- `PLGW-113` Add `/api/v1/health` with adapter diagnostics.

### Phase C: Dashboard MVP

Goal: usable live UI for concurrency and failure drill-down.

Tickets:
- `PLGW-120` Build `/live` concurrency lanes and status chips.
- `PLGW-121` Build `/timeline` with filters and virtualization.
- `PLGW-122` Build detail drawer with payload inspector.
- `PLGW-123` Add `/runs` index and run details panel.

### Phase D: Replay, Export, and Hardening

Goal: production-ready local tool quality.

Tickets:
- `PLGW-130` Implement replay scrubber and deterministic playback.
- `PLGW-131` Add command-level export (`json`, optional `csv`).
- `PLGW-132` Add redaction, retention controls, and security gates.
- `PLGW-133` Add performance soak tests and reliability fixes.

## 13. Implementation Checklist

### Backend

- [ ] Canonical schema module committed with fixtures.
- [ ] Adapter framework with `opencode-sse` and `claude-hooks` implemented.
- [ ] SQLite migration and index strategy in place.
- [ ] REST + SSE endpoints implemented and documented.
- [ ] Health endpoint includes adapter freshness and queue depth.

### Frontend

- [ ] Live lanes and nested session rendering complete.
- [ ] Timeline filtering and event details complete.
- [ ] Replay controls complete.
- [ ] Keyboard shortcuts and reduced-motion support complete.

### CLI

- [ ] `/plugwalk` start/stop/status implemented.
- [ ] replay/export flags implemented and validated.
- [ ] Helpful startup and error messaging added.

### Quality

- [ ] Unit/integration/UI tests pass.
- [ ] Soak test run with concurrency fixture.
- [ ] Security redaction tests pass.

## 14. Open Questions

1. Should CSV export be in v1 or deferred to v1.1?
2. Should incident clustering be heuristic-only in v1, or include explicit rule packs?
3. Should non-local bind be enabled in v1 behind a token requirement?
