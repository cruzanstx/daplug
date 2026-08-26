"""Tests for the agy_stream line-oriented parser.

Fixture lines are captured from a real ``agy --output-format stream-json`` run
(agy 1.1.20).  Do not invent schemas — every fixture line is real output.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

import agy_stream


# --- Real fixture lines from agy 1.1.20 --------------------------------

_INIT_LINE = (
    '{"event":"init","conversation_id":"c78dfbed-6231-4782-abc6-d3334c19ea5d",'
    '"init":{"model":"Gemini 3.7 Flash (High)","cwd":"/tmp","tools":["run_command"],'
    '"permission_mode":"always-proceed"}}'
)

_STEP_USER_INPUT = (
    '{"event":"step_update","step_update":{"conversation_id":"c78dfbed-6231-4782-abc6-d3334c19ea5d",'
    '"step_index":0,"state":"DONE","step_type":"user_input"}}'
)

_STEP_CHECKPOINT = (
    '{"event":"step_update","step_update":{"conversation_id":"c78dfbed-6231-4782-abc6-d3334c19ea5d",'
    '"step_index":1,"state":"DONE","step_type":"checkpoint","duration_seconds":2.0}}'
)

_STEP_TEXT_DELTA_PONG = (
    '{"event":"step_update","step_update":{"conversation_id":"c78dfbed-6231-4782-abc6-d3334c19ea5d",'
    '"step_index":2,"state":"ACTIVE","step_type":"agent_response","text_delta":"PONG"}}'
)

_STEP_TEXT_DELTA_NEWLINE = (
    '{"event":"step_update","step_update":{"conversation_id":"c78dfbed-6231-4782-abc6-d3334c19ea5d",'
    '"step_index":2,"state":"DONE","step_type":"agent_response","text_delta":"\\n",'
    '"duration_seconds":1.3,"usage":{"input_tokens":18994,"output_tokens":35}}}'
)

_RESULT_SUCCESS = (
    '{"event":"result","result":{"conversation_id":"c78dfbed-6231-4782-abc6-d3334c19ea5d",'
    '"status":"SUCCESS","response":"PONG\\n","duration_seconds":3.5,'
    '"num_turns":1,"usage":{"input_tokens":18994,"output_tokens":35}}}'
)

_RESULT_TIMEOUT = (
    '{"event":"result","result":{"conversation_id":"cc40f589-fa0b-40e5-91ca-6af59e53bac4",'
    '"status":"ERROR","response":"","error":"timeout waiting for response",'
    '"duration_seconds":1.3,"num_turns":1,"usage":{"input_tokens":0,"output_tokens":0}}}'
)

_RESULT_ERROR = (
    '{"event":"result","result":{"conversation_id":"abc-123",'
    '"status":"ERROR","response":"","error":"model overloaded",'
    '"duration_seconds":1.0,"num_turns":1,"usage":{"input_tokens":0,"output_tokens":0}}}'
)


# --- parse_line tests --------------------------------------------------


class TestParseLine:
    def test_init_event_parsed_as_progress(self):
        event = agy_stream.parse_line(_INIT_LINE)
        assert event.event_type == agy_stream.EVENT_PROGRESS
        assert event.conversation_id == "c78dfbed-6231-4782-abc6-d3334c19ea5d"

    def test_step_update_without_text_delta_is_progress(self):
        event = agy_stream.parse_line(_STEP_USER_INPUT)
        assert event.event_type == agy_stream.EVENT_PROGRESS
        assert event.conversation_id == "c78dfbed-6231-4782-abc6-d3334c19ea5d"
        assert event.text is None

    def test_step_update_checkpoint_is_progress(self):
        event = agy_stream.parse_line(_STEP_CHECKPOINT)
        assert event.event_type == agy_stream.EVENT_PROGRESS
        assert event.conversation_id == "c78dfbed-6231-4782-abc6-d3334c19ea5d"

    def test_step_update_with_text_delta_is_assistant_text(self):
        event = agy_stream.parse_line(_STEP_TEXT_DELTA_PONG)
        assert event.event_type == agy_stream.EVENT_ASSISTANT_TEXT
        assert event.text == "PONG"
        assert event.conversation_id == "c78dfbed-6231-4782-abc6-d3334c19ea5d"

    def test_step_update_with_newline_text_delta(self):
        event = agy_stream.parse_line(_STEP_TEXT_DELTA_NEWLINE)
        assert event.event_type == agy_stream.EVENT_ASSISTANT_TEXT
        assert event.text == "\n"

    def test_result_success_event(self):
        event = agy_stream.parse_line(_RESULT_SUCCESS)
        assert event.event_type == agy_stream.EVENT_RESULT
        assert event.conversation_id == "c78dfbed-6231-4782-abc6-d3334c19ea5d"
        assert event.status == "SUCCESS"
        assert event.text == "PONG\n"
        assert event.error is None

    def test_result_timeout_event(self):
        event = agy_stream.parse_line(_RESULT_TIMEOUT)
        assert event.event_type == agy_stream.EVENT_RESULT
        assert event.status == "ERROR"
        assert event.error == "timeout waiting for response"
        assert event.conversation_id == "cc40f589-fa0b-40e5-91ca-6af59e53bac4"

    def test_result_error_event(self):
        event = agy_stream.parse_line(_RESULT_ERROR)
        assert event.event_type == agy_stream.EVENT_RESULT
        assert event.status == "ERROR"
        assert event.error == "model overloaded"

    def test_non_json_line_tolerated(self):
        event = agy_stream.parse_line("this is not json")
        assert event.event_type == agy_stream.EVENT_UNKNOWN
        assert event.raw == "this is not json"

    def test_empty_line_tolerated(self):
        event = agy_stream.parse_line("")
        assert event.event_type == agy_stream.EVENT_UNKNOWN
        assert event.raw == ""

    def test_partial_json_tolerated(self):
        event = agy_stream.parse_line('{"event":"result","result":')
        assert event.event_type == agy_stream.EVENT_UNKNOWN

    def test_json_array_tolerated(self):
        event = agy_stream.parse_line("[1,2,3]")
        assert event.event_type == agy_stream.EVENT_UNKNOWN

    def test_unknown_event_name(self):
        event = agy_stream.parse_line('{"event":"future_event","data":"x"}')
        assert event.event_type == agy_stream.EVENT_UNKNOWN


# --- is_terminal / is_success / is_error / is_print_timeout ------------


class TestEventClassification:
    def test_is_terminal_true_for_result(self):
        event = agy_stream.parse_line(_RESULT_SUCCESS)
        assert agy_stream.is_terminal(event) is True

    def test_is_terminal_false_for_progress(self):
        event = agy_stream.parse_line(_INIT_LINE)
        assert agy_stream.is_terminal(event) is False

    def test_is_success_true_for_success_status(self):
        event = agy_stream.parse_line(_RESULT_SUCCESS)
        assert agy_stream.is_success(event) is True

    def test_is_success_false_for_error_status(self):
        event = agy_stream.parse_line(_RESULT_ERROR)
        assert agy_stream.is_success(event) is False

    def test_is_success_false_for_empty_status(self):
        """A result event with no status must not be treated as success."""
        event = agy_stream.AgyEvent(
            event_type=agy_stream.EVENT_RESULT,
            raw="",
            status=None,
        )
        assert agy_stream.is_success(event) is False

    def test_is_success_false_for_cancelled_status(self):
        """CANCELLED is not a success status."""
        event = agy_stream.AgyEvent(
            event_type=agy_stream.EVENT_RESULT,
            raw="",
            status="CANCELLED",
        )
        assert agy_stream.is_success(event) is False

    def test_is_error_true_for_error_status(self):
        event = agy_stream.parse_line(_RESULT_ERROR)
        assert agy_stream.is_error(event) is True

    def test_is_error_false_for_success_status(self):
        event = agy_stream.parse_line(_RESULT_SUCCESS)
        assert agy_stream.is_error(event) is False

    def test_is_print_timeout_true_for_timeout_error(self):
        event = agy_stream.parse_line(_RESULT_TIMEOUT)
        assert agy_stream.is_print_timeout(event) is True

    def test_is_print_timeout_false_for_non_timeout_error(self):
        event = agy_stream.parse_line(_RESULT_ERROR)
        assert agy_stream.is_print_timeout(event) is False

    def test_is_print_timeout_false_for_generic_timeout_text(self):
        """Narrowed: generic timeout phrases must not match."""
        event = agy_stream.AgyEvent(
            event_type=agy_stream.EVENT_RESULT,
            raw="",
            status="ERROR",
            error="request timeout: network",
        )
        assert agy_stream.is_print_timeout(event) is False

    def test_is_print_timeout_false_for_success(self):
        event = agy_stream.parse_line(_RESULT_SUCCESS)
        assert agy_stream.is_print_timeout(event) is False


# --- extract_assistant_text -------------------------------------------


class TestExtractAssistantText:
    def test_extracts_text_deltas_and_response(self):
        lines = [
            _INIT_LINE,
            _STEP_USER_INPUT,
            _STEP_CHECKPOINT,
            _STEP_TEXT_DELTA_PONG,
            _STEP_TEXT_DELTA_NEWLINE,
            _RESULT_SUCCESS,
        ]
        text = agy_stream.extract_assistant_text(lines)
        assert "PONG" in text
        assert "PONG\n" in text  # response from result event

    def test_skips_non_json_lines(self):
        text = agy_stream.extract_assistant_text(["not json", "", "random"])
        assert text == ""

    def test_extracts_text_with_verification_marker(self):
        marker_text = (
            '{"event":"step_update","step_update":{"conversation_id":"x",'
            '"step_index":0,"state":"ACTIVE","step_type":"agent_response",'
            '"text_delta":"<verification>VERIFICATION_COMPLETE</verification>"}}'
        )
        lines = [marker_text]
        text = agy_stream.extract_assistant_text(lines)
        assert "<verification>VERIFICATION_COMPLETE</verification>" in text


# --- Conversation ID extraction ----------------------------------------


class TestConversationId:
    def test_conversation_id_from_init(self):
        event = agy_stream.parse_line(_INIT_LINE)
        assert event.conversation_id == "c78dfbed-6231-4782-abc6-d3334c19ea5d"

    def test_conversation_id_from_step_update(self):
        event = agy_stream.parse_line(_STEP_TEXT_DELTA_PONG)
        assert event.conversation_id == "c78dfbed-6231-4782-abc6-d3334c19ea5d"

    def test_conversation_id_from_result(self):
        event = agy_stream.parse_line(_RESULT_SUCCESS)
        assert event.conversation_id == "c78dfbed-6231-4782-abc6-d3334c19ea5d"

    def test_different_conversation_id_in_timeout(self):
        event = agy_stream.parse_line(_RESULT_TIMEOUT)
        assert event.conversation_id == "cc40f589-fa0b-40e5-91ca-6af59e53bac4"
