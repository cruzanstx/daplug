import importlib.util
import json
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest


def _load_module():
    root = Path(__file__).resolve().parents[3]
    script = root / "skills" / "at-prompt-runner" / "scripts" / "at_runner.py"
    spec = importlib.util.spec_from_file_location("at_runner", script)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules["at_runner"] = module
    spec.loader.exec_module(module)
    return module


m = _load_module()


# ---------------------------------------------------------------------------
# parse_group_syntax
# ---------------------------------------------------------------------------

class TestParseGroupSyntax:
    def test_single_prompt(self):
        result = m.parse_group_syntax("220")
        assert len(result) == 1
        assert result[0]["phase"] == 1
        assert result[0]["prompts"] == [220]
        assert result[0]["strategy"] == "parallel"

    def test_parallel_within_phase(self):
        result = m.parse_group_syntax("220,221")
        assert len(result) == 1
        assert result[0]["prompts"] == [220, 221]

    def test_sequential_phases(self):
        result = m.parse_group_syntax("220,221 -> 222,223 -> 224")
        assert len(result) == 3
        assert result[0]["prompts"] == [220, 221]
        assert result[1]["prompts"] == [222, 223]
        assert result[2]["prompts"] == [224]
        assert result[0]["phase"] == 1
        assert result[1]["phase"] == 2
        assert result[2]["phase"] == 3

    def test_space_separated_within_phase(self):
        result = m.parse_group_syntax("220 221 222")
        assert len(result) == 1
        assert result[0]["prompts"] == [220, 221, 222]

    def test_mixed_comma_and_space(self):
        result = m.parse_group_syntax("220, 221 222")
        assert len(result) == 1
        assert set(result[0]["prompts"]) == {220, 221, 222}

    def test_deduplication(self):
        result = m.parse_group_syntax("220,220,221")
        assert result[0]["prompts"] == [220, 221]

    def test_empty_string_raises(self):
        with pytest.raises(ValueError, match="cannot be empty"):
            m.parse_group_syntax("")

    def test_whitespace_only_raises(self):
        with pytest.raises(ValueError, match="cannot be empty"):
            m.parse_group_syntax("   ")

    def test_empty_phase_raises(self):
        with pytest.raises(ValueError, match="empty phase"):
            m.parse_group_syntax("220 -> -> 222")

    def test_trailing_arrow_raises(self):
        with pytest.raises(ValueError, match="empty phase"):
            m.parse_group_syntax("220 ->")

    def test_leading_arrow_raises(self):
        with pytest.raises(ValueError, match="empty phase"):
            m.parse_group_syntax("-> 220")

    def test_extra_whitespace_is_trimmed(self):
        result = m.parse_group_syntax("  220 , 221  ->  222  ")
        assert len(result) == 2
        assert result[0]["prompts"] == [220, 221]
        assert result[1]["prompts"] == [222]


# ---------------------------------------------------------------------------
# normalize_prompt_token
# ---------------------------------------------------------------------------

class TestNormalizePromptToken:
    def test_plain_number(self):
        assert m.normalize_prompt_token("220") == 220

    def test_zero_padded(self):
        assert m.normalize_prompt_token("005") == 5

    def test_folder_prefix(self):
        assert m.normalize_prompt_token("providers/011") == "providers/011"

    def test_nested_folder(self):
        assert m.normalize_prompt_token("a/b/003") == "a/b/003"

    def test_empty_raises(self):
        with pytest.raises(ValueError, match="Empty prompt token"):
            m.normalize_prompt_token("")

    def test_invalid_token_raises(self):
        with pytest.raises(ValueError, match="Invalid prompt token"):
            m.normalize_prompt_token("not-a-number")


# ---------------------------------------------------------------------------
# parse_prompt_list
# ---------------------------------------------------------------------------

class TestParsePromptList:
    def test_simple_list(self):
        result = m.parse_prompt_list("220 221 222")
        assert result == [220, 221, 222]

    def test_commas(self):
        result = m.parse_prompt_list("220,221,222")
        assert result == [220, 221, 222]

    def test_strips_arrows(self):
        """Arrows are treated as whitespace in prompt list mode."""
        result = m.parse_prompt_list("220 -> 221 -> 222")
        assert result == [220, 221, 222]

    def test_deduplication(self):
        result = m.parse_prompt_list("220 220 221")
        assert result == [220, 221]

    def test_empty_raises(self):
        with pytest.raises(ValueError, match="No prompts"):
            m.parse_prompt_list("")


# ---------------------------------------------------------------------------
# build_execution_plan
# ---------------------------------------------------------------------------

class TestBuildExecutionPlan:
    def test_single_phase_plan(self):
        phases = [{"phase": 1, "prompts": [215], "strategy": "parallel"}]
        plan = m.build_execution_plan(phases, "codex-xhigh", {"worktree": True, "loop": True, "validate": False, "dry_run": False})

        assert plan["model"] == "codex-xhigh"
        assert plan["total_phases"] == 1
        assert plan["total_prompts"] == 1
        assert len(plan["phases"]) == 1
        cmd = plan["phases"][0]["commands"][0]["command"]
        assert cmd == "/run-prompt 215 --model codex-xhigh --worktree --loop"

    def test_multi_phase_plan(self):
        phases = [
            {"phase": 1, "prompts": [220, 221], "strategy": "parallel"},
            {"phase": 2, "prompts": [222], "strategy": "parallel"},
        ]
        plan = m.build_execution_plan(phases, "codex", {"worktree": False, "loop": False, "validate": False, "dry_run": False})

        assert plan["total_phases"] == 2
        assert plan["total_prompts"] == 3
        assert len(plan["phases"][0]["commands"]) == 2
        assert plan["phases"][0]["commands"][0]["command"] == "/run-prompt 220 --model codex"
        assert plan["phases"][0]["commands"][1]["command"] == "/run-prompt 221 --model codex"
        assert plan["phases"][1]["commands"][0]["command"] == "/run-prompt 222 --model codex"

    def test_validate_flag_adds_post_phase(self):
        phases = [{"phase": 1, "prompts": [215], "strategy": "parallel"}]
        plan = m.build_execution_plan(phases, "codex", {"worktree": False, "loop": False, "validate": True, "dry_run": False})
        assert plan["post_phase"] == "at-validator"

    def test_no_validate_flag_no_post_phase(self):
        phases = [{"phase": 1, "prompts": [215], "strategy": "parallel"}]
        plan = m.build_execution_plan(phases, "codex", {"worktree": False, "loop": False, "validate": False, "dry_run": False})
        assert "post_phase" not in plan

    def test_folder_prefixed_prompt(self):
        phases = [{"phase": 1, "prompts": ["providers/011"], "strategy": "parallel"}]
        plan = m.build_execution_plan(phases, "gemini", {"worktree": True, "loop": False, "validate": False, "dry_run": False})
        cmd = plan["phases"][0]["commands"][0]["command"]
        assert cmd == "/run-prompt providers/011 --model gemini --worktree"

    def test_run_commands_summary(self):
        phases = [
            {"phase": 1, "prompts": [220, 221], "strategy": "parallel"},
            {"phase": 2, "prompts": [222], "strategy": "parallel"},
        ]
        plan = m.build_execution_plan(phases, "codex", {"worktree": False, "loop": False, "validate": False, "dry_run": False})
        rc = plan["run_commands"]
        assert len(rc) == 2
        assert rc[0]["phase"] == 1
        assert len(rc[0]["commands"]) == 2
        assert rc[1]["phase"] == 2
        assert len(rc[1]["commands"]) == 1


# ---------------------------------------------------------------------------
# _classify_prompt
# ---------------------------------------------------------------------------

class TestClassifyPrompt:
    def test_validation_keywords(self):
        assert m._classify_prompt("Run all unit tests and validate output") == "validation"
        assert m._classify_prompt("Lint the codebase") == "validation"

    def test_setup_keywords(self):
        assert m._classify_prompt("Bootstrap the database schema") == "setup"
        assert m._classify_prompt("Initialize project structure") == "setup"

    def test_implementation_default(self):
        assert m._classify_prompt("Add user authentication feature") == "implementation"
        assert m._classify_prompt("Refactor the API layer") == "implementation"


# ---------------------------------------------------------------------------
# _extract_dependency_refs
# ---------------------------------------------------------------------------

class TestExtractDependencyRefs:
    def test_explicit_depends_on(self):
        text = "depends_on: 220, 221"
        refs = [220, 221, 222]
        deps = m._extract_dependency_refs(text, refs, 222)
        assert "220" in deps
        assert "221" in deps

    def test_phrase_dependency(self):
        text = "This task depends on prompt 220 being completed first."
        refs = [220, 221]
        deps = m._extract_dependency_refs(text, refs, 221)
        assert "220" in deps

    def test_no_self_dependency(self):
        text = "depends_on: 220"
        refs = [220, 221]
        deps = m._extract_dependency_refs(text, refs, 220)
        assert "220" not in deps

    def test_no_deps_found(self):
        text = "Implement a new feature for the dashboard."
        refs = [220, 221]
        deps = m._extract_dependency_refs(text, refs, 220)
        assert len(deps) == 0


# ---------------------------------------------------------------------------
# _topological_phases
# ---------------------------------------------------------------------------

class TestTopologicalPhases:
    def test_no_deps_all_parallel(self):
        refs = [220, 221, 222]
        deps = {"220": set(), "221": set(), "222": set()}
        phases, cycle = m._topological_phases(refs, deps)
        assert len(phases) == 1
        assert set(phases[0]) == {220, 221, 222}
        assert cycle == []

    def test_linear_chain(self):
        refs = [220, 221, 222]
        deps = {"220": set(), "221": {"220"}, "222": {"221"}}
        phases, cycle = m._topological_phases(refs, deps)
        assert len(phases) == 3
        assert phases[0] == [220]
        assert phases[1] == [221]
        assert phases[2] == [222]
        assert cycle == []

    def test_diamond_dependency(self):
        refs = [1, 2, 3, 4]
        deps = {"1": set(), "2": {"1"}, "3": {"1"}, "4": {"2", "3"}}
        phases, cycle = m._topological_phases(refs, deps)
        assert len(phases) == 3
        assert phases[0] == [1]
        assert set(phases[1]) == {2, 3}
        assert phases[2] == [4]
        assert cycle == []

    def test_cycle_detection(self):
        refs = [220, 221]
        deps = {"220": {"221"}, "221": {"220"}}
        phases, cycle = m._topological_phases(refs, deps)
        assert len(cycle) > 0


# ---------------------------------------------------------------------------
# infer_auto_dependencies (with mocked prompt reads)
# ---------------------------------------------------------------------------

class TestInferAutoDependencies:
    def _mock_read(self, content_map):
        """Return a side_effect function for _prompt_manager_read."""
        def _read(paths, ref):
            key = m._prompt_ref_key(ref)
            if key in content_map:
                return content_map[key]
            raise RuntimeError(f"Not found: {ref}")
        return _read

    @patch.object(m, '_prompt_manager_read')
    def test_no_deps_all_parallel(self, mock_read):
        mock_read.side_effect = self._mock_read({
            "220": "Implement user auth",
            "221": "Implement dashboard",
        })
        phases, meta = m.infer_auto_dependencies([220, 221], MagicMock())
        assert len(phases) == 1
        assert set(phases[0]["prompts"]) == {220, 221}
        assert not meta["cycle_detected"]

    @patch.object(m, '_prompt_manager_read')
    def test_explicit_dependency_creates_phases(self, mock_read):
        mock_read.side_effect = self._mock_read({
            "220": "Setup the database schema",
            "221": "depends_on: 220\nImplement the API layer",
        })
        phases, meta = m.infer_auto_dependencies([220, 221], MagicMock())
        assert len(phases) == 2
        assert phases[0]["prompts"] == [220]
        assert phases[1]["prompts"] == [221]

    @patch.object(m, '_prompt_manager_read')
    def test_validation_heuristic(self, mock_read):
        mock_read.side_effect = self._mock_read({
            "220": "Implement the feature",
            "221": "Run all unit tests and validate",
        })
        phases, meta = m.infer_auto_dependencies([220, 221], MagicMock())
        # Validation should be after implementation
        assert len(phases) == 2
        assert phases[0]["prompts"] == [220]
        assert phases[1]["prompts"] == [221]
        assert meta["classifications"]["221"] == "validation"

    @patch.object(m, '_prompt_manager_read')
    def test_setup_heuristic(self, mock_read):
        mock_read.side_effect = self._mock_read({
            "220": "Bootstrap the database schema",
            "221": "Implement the API layer",
        })
        phases, meta = m.infer_auto_dependencies([220, 221], MagicMock())
        assert len(phases) == 2
        assert phases[0]["prompts"] == [220]
        assert phases[1]["prompts"] == [221]
        assert meta["classifications"]["220"] == "setup"

    @patch.object(m, '_prompt_manager_read')
    def test_cycle_falls_back_to_sequential(self, mock_read):
        mock_read.side_effect = self._mock_read({
            "220": "depends_on: 221",
            "221": "depends_on: 220",
        })
        phases, meta = m.infer_auto_dependencies([220, 221], MagicMock())
        # Cycle detected -> sequential fallback
        assert meta["cycle_detected"]
        assert len(phases) == 2
        assert phases[0]["prompts"] == [220]
        assert phases[1]["prompts"] == [221]

    @patch.object(m, '_prompt_manager_read')
    def test_read_error_handled_gracefully(self, mock_read):
        mock_read.side_effect = RuntimeError("Not found")
        phases, meta = m.infer_auto_dependencies([220, 221], MagicMock())
        assert len(meta["read_errors"]) == 2
        # Should still produce phases (all parallel, no content to analyze)
        assert len(phases) == 1


# ---------------------------------------------------------------------------
# collect_prompt_refs
# ---------------------------------------------------------------------------

class TestCollectPromptRefs:
    def test_collects_and_dedupes(self):
        phases = [
            {"phase": 1, "prompts": [220, 221]},
            {"phase": 2, "prompts": [221, 222]},
        ]
        refs = m.collect_prompt_refs(phases)
        assert refs == [220, 221, 222]


# ---------------------------------------------------------------------------
# format_run_commands
# ---------------------------------------------------------------------------

class TestFormatRunCommands:
    def test_extracts_commands(self):
        plan = {
            "phases": [
                {
                    "phase": 1,
                    "strategy": "parallel",
                    "commands": [
                        {"prompt": 220, "command": "/run-prompt 220 --model codex"},
                        {"prompt": 221, "command": "/run-prompt 221 --model codex"},
                    ],
                },
                {
                    "phase": 2,
                    "strategy": "parallel",
                    "commands": [
                        {"prompt": 222, "command": "/run-prompt 222 --model codex"},
                    ],
                },
            ]
        }
        result = m.format_run_commands(plan)
        assert len(result) == 2
        assert result[0]["commands"] == ["/run-prompt 220 --model codex", "/run-prompt 221 --model codex"]
        assert result[1]["commands"] == ["/run-prompt 222 --model codex"]


# ---------------------------------------------------------------------------
# CLI integration (cmd_parse via main)
# ---------------------------------------------------------------------------

class TestCLIIntegration:
    def test_parse_command_exits_zero(self):
        with patch.object(sys, 'argv', ['at_runner', 'parse', '220,221 -> 222']):
            assert m.main() == 0

    def test_parse_empty_exits_one(self):
        with patch.object(sys, 'argv', ['at_runner', 'parse', '']):
            assert m.main() == 1
