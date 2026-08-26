#!/usr/bin/env python3
"""Pure line-oriented parser for agy ``--output-format stream-json`` output.

Each stdout line from agy's stream-json mode is a self-contained JSON object
with an ``event`` field identifying the event type.  This module classifies
lines into typed events, extracts assistant text and terminal metadata
(``conversation_id``, ``status``), and tolerates non-JSON / partial lines
without raising.

Observed event shapes (agy 1.1.20, ``--output-format stream-json``):

    {"event":"init","conversation_id":"<uuid>","init":{...}}
    {"event":"step_update","step_update":{"conversation_id":"<uuid>","step_index":N,"state":"DONE|ACTIVE","step_type":"user_input|checkpoint|agent_response","text_delta":"..."}}
    {"event":"result","result":{"conversation_id":"<uuid>","status":"SUCCESS|ERROR","response":"...","error":"...(on error)...","duration_seconds":N,"num_turns":N,"usage":{...}}}

On agy's own ``--print-timeout`` the terminal result event carries
``status:"ERROR"`` and ``error:"timeout waiting for response"`` with exit
code 1.

The parser performs no I/O so it can be unit-tested with fixture strings.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Optional

EVENT_PROGRESS = "progress"
EVENT_TOOL = "tool"
EVENT_ASSISTANT_TEXT = "assistant_text"
EVENT_RESULT = "result"
EVENT_UNKNOWN = "unknown"


@dataclass(frozen=True)
class AgyEvent:
    """Typed classification of one stream-json line."""

    event_type: str
    raw: str
    text: Optional[str] = None
    conversation_id: Optional[str] = None
    status: Optional[str] = None
    error: Optional[str] = None
    tool_name: Optional[str] = None
    extra: dict = field(default_factory=dict)


def parse_line(line: str) -> AgyEvent:
    """Parse one stdout line into an :class:`AgyEvent`.

    Non-JSON lines, partial JSON, and empty lines are returned as
    ``EVENT_UNKNOWN`` with ``raw`` set to the stripped input.  The function
    never raises.
    """
    stripped = line.rstrip("\n\r")
    if not stripped.strip():
        return AgyEvent(event_type=EVENT_UNKNOWN, raw=stripped)

    try:
        data = json.loads(stripped)
    except (json.JSONDecodeError, ValueError):
        return AgyEvent(event_type=EVENT_UNKNOWN, raw=stripped)

    if not isinstance(data, dict):
        return AgyEvent(event_type=EVENT_UNKNOWN, raw=stripped)

    event_name = str(data.get("event", "")).lower()
    conv_id = _str(data.get("conversation_id"))

    if event_name == "result":
        return _parse_result_event(stripped, data, conv_id)

    if event_name == "step_update":
        return _parse_step_update_event(stripped, data, conv_id)

    if event_name == "init":
        return _parse_init_event(stripped, data, conv_id)

    if event_name in ("text", "text_delta", "assistant_text", "message"):
        return _parse_text_event(stripped, data, conv_id)

    if event_name in ("tool", "tool_call", "tool_result", "function_call"):
        return _parse_tool_event(stripped, data, conv_id)

    if event_name in ("progress", "thinking", "step", "status"):
        return AgyEvent(
            event_type=EVENT_PROGRESS,
            raw=stripped,
            conversation_id=conv_id,
            extra=_extra(data, {"event", "conversation_id"}),
        )

    return AgyEvent(
        event_type=EVENT_UNKNOWN,
        raw=stripped,
        conversation_id=conv_id,
        extra={k: v for k, v in data.items() if k != "event"},
    )


def _parse_result_event(raw: str, data: dict, conv_id: Optional[str]) -> AgyEvent:
    result = data.get("result") or data
    if not isinstance(result, dict):
        result = {}
    return AgyEvent(
        event_type=EVENT_RESULT,
        raw=raw,
        text=_str(result.get("response")),
        conversation_id=_str(result.get("conversation_id")) or conv_id,
        status=_str(result.get("status")),
        error=_str(result.get("error")) or None,
        extra=_extra(data, {"event", "result", "conversation_id"}),
    )


def _parse_step_update_event(raw: str, data: dict, conv_id: Optional[str]) -> AgyEvent:
    step = data.get("step_update") or {}
    if not isinstance(step, dict):
        step = {}
    step_conv = _str(step.get("conversation_id")) or conv_id
    text_delta = _str(step.get("text_delta"))
    step_type = _str(step.get("step_type"))

    if text_delta:
        return AgyEvent(
            event_type=EVENT_ASSISTANT_TEXT,
            raw=raw,
            text=text_delta,
            conversation_id=step_conv,
            extra=_extra(step, {"conversation_id", "text_delta", "step_type"}),
        )

    return AgyEvent(
        event_type=EVENT_PROGRESS,
        raw=raw,
        conversation_id=step_conv,
        extra=_extra(step, {"conversation_id", "text_delta", "step_type"}),
    )


def _parse_init_event(raw: str, data: dict, conv_id: Optional[str]) -> AgyEvent:
    init = data.get("init") or {}
    if not isinstance(init, dict):
        init = {}
    init_conv = _str(init.get("conversation_id")) or conv_id
    return AgyEvent(
        event_type=EVENT_PROGRESS,
        raw=raw,
        conversation_id=init_conv,
        extra=_extra(init, {"conversation_id", "model", "tools", "permission_mode"}),
    )


def _parse_text_event(raw: str, data: dict, conv_id: Optional[str]) -> AgyEvent:
    text = (
        _str(data.get("text"))
        or _str(data.get("delta"))
        or _str(data.get("content"))
        or _str(data.get("response"))
    )
    return AgyEvent(
        event_type=EVENT_ASSISTANT_TEXT,
        raw=raw,
        text=text,
        conversation_id=conv_id,
        extra=_extra(data, {"event", "text", "delta", "content", "response", "conversation_id"}),
    )


def _parse_tool_event(raw: str, data: dict, conv_id: Optional[str]) -> AgyEvent:
    tool = data.get("tool") or data.get("tool_call") or data
    tool_name = None
    if isinstance(tool, dict):
        tool_name = _str(tool.get("name")) or _str(tool.get("tool_name"))
    if not tool_name:
        tool_name = _str(data.get("name")) or _str(data.get("tool_name"))
    return AgyEvent(
        event_type=EVENT_TOOL,
        raw=raw,
        tool_name=tool_name,
        conversation_id=conv_id,
        extra=_extra(data, {"event", "tool", "tool_call", "name", "tool_name", "conversation_id"}),
    )


def is_terminal(event: AgyEvent) -> bool:
    """True when *event* is a terminal result event."""
    return event.event_type == EVENT_RESULT


def is_success(event: AgyEvent) -> bool:
    """True when *event* is a terminal result with a success status.

    An empty/missing status is NOT success — it is unknown and must classify
    as ``agy_error`` per the failure-classification requirements.
    """
    if event.event_type != EVENT_RESULT:
        return False
    status = (event.status or "").upper()
    return status in ("SUCCESS", "OK", "COMPLETED", "DONE")


def is_error(event: AgyEvent) -> bool:
    """True when *event* is a terminal result with an error status."""
    if event.event_type != EVENT_RESULT:
        return False
    status = (event.status or "").upper()
    return status in ("ERROR", "FAILED", "FAILURE")


def is_print_timeout(event: AgyEvent) -> bool:
    """True when *event* indicates agy's own --print-timeout fired.

    agy emits a result event with ``status`` set to ``ERROR`` and an
    ``error`` field containing ``timeout waiting for response``.  We match
    case-insensitively on that exact signature to avoid classifying
    arbitrary network/API timeout text as a print timeout.
    """
    if event.event_type != EVENT_RESULT:
        return False
    text = (event.error or "").lower()
    return "timeout waiting for response" in text


def extract_assistant_text(lines: list[str]) -> str:
    """Convenience: extract all assistant text from a list of raw lines.

    Concatenates text deltas and the terminal ``response`` field.
    Non-JSON lines are skipped silently.
    """
    parts: list[str] = []
    for line in lines:
        event = parse_line(line)
        if event.event_type == EVENT_ASSISTANT_TEXT and event.text:
            parts.append(event.text)
        elif event.event_type == EVENT_RESULT and event.text:
            parts.append(event.text)
    return "\n".join(parts)


def _str(value) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, str):
        return value if value else None
    return str(value)


def _extra(data: dict, skip: set[str]) -> dict:
    return {k: v for k, v in data.items() if k not in skip}
