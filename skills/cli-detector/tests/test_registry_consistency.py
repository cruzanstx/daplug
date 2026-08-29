"""Consistency tests: ensure router._SHORTHAND and scripts/models.json agree.

``scripts/models.json`` is the single source of truth for daplug model
shorthands (prompt 245).  ``router.py`` maintains its own ``_SHORTHAND``
dict for routing.  These tests catch drift between the two so CI fails
before shipping a model that routes incorrectly.

Design decision: we chose a consistency test (design b) over loading
models.json at import time (design a) because the router has
implementation-specific fields -- ``force_cli``, ``strict_cli``,
``local_hint``, ``capabilities`` -- that are routing internals, not model
metadata.  Adding them to models.json would couple the registry to router
implementation details.  The test is the CI tripwire that catches drift
without risking behavior change.

See prompts/reports/246-router-consistency-report.md for the full
rationale and drift audit.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import pytest

SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

import router  # noqa: E402


# --- Path resolution --------------------------------------------------

_REPO_ROOT = Path(__file__).resolve().parents[3]
_REGISTRY_PATH = _REPO_ROOT / "scripts" / "models.json"


# --- Family mapping ---------------------------------------------------

# models.json docs.family uses display names; router uses internal family
# identifiers.  This mapping bridges the two so the consistency test can
# compare them.
_FAMILY_MAP: dict[str, str] = {
    "Claude": "anthropic",
    "OpenAI Codex": "openai",
    "Google Gemini": "google",
    "Z.AI / OpenCode": "zai",
    "Synthetic": "synthetic",
    "Local": "local",
}


# --- Helpers ----------------------------------------------------------


class _FakeCache:
    """Minimal stand-in for the CLI detection cache used by router.resolve_model."""

    def __init__(self, data: dict):
        self._data = data

    def to_dict(self) -> dict:
        return dict(self._data)


def _load_registry() -> list[dict]:
    """Load and return the models list from scripts/models.json."""
    if not _REGISTRY_PATH.exists():
        pytest.fail(f"Model registry not found: {_REGISTRY_PATH}")
    data = json.loads(_REGISTRY_PATH.read_text())
    models = data.get("models")
    if not isinstance(models, list):
        pytest.fail(f"models.json 'models' is not a list: {type(models)}")
    return models


def _derive_reasoning_effort(
    name: str, supports_codex_reasoning: bool
) -> str | None:
    """Derive expected reasoning_effort from model name and supports flag.

    The router sets ``reasoning_effort`` only for models that support
    codex reasoning (``-c model_reasoning_effort=...``).  Gemini models
    with ``-high``/``-xhigh`` suffixes use different model IDs instead,
    so their ``reasoning_effort`` must be ``None``.
    """
    if not supports_codex_reasoning:
        return None
    if name.endswith("-high"):
        return "high"
    if name.endswith("-xhigh"):
        return "xhigh"
    return None


def _collect_drifts(
    registry_models: list[dict],
    shorthand: dict[str, router._ModelRequest],
) -> list[str]:
    """Return a list of human-readable drift messages.

    An empty list means no drift.  Each message names the shorthand and
    the specific field that disagrees, so the output is directly
    actionable.
    """
    drifts: list[str] = []

    registry_names = {m["name"] for m in registry_models}
    router_names = set(shorthand.keys())

    only_registry = sorted(registry_names - router_names)
    only_router = sorted(router_names - registry_names)
    if only_registry:
        drifts.append(
            "shorthands in models.json but missing from router._SHORTHAND: "
            + str(only_registry)
        )
    if only_router:
        drifts.append(
            "shorthands in router._SHORTHAND but missing from models.json: "
            + str(only_router)
        )

    reg_by_name = {m["name"]: m for m in registry_models}
    for name in sorted(registry_names & router_names):
        reg = reg_by_name[name]
        req = shorthand[name]

        # Family
        reg_family_display = reg["docs"]["family"]
        reg_family = _FAMILY_MAP.get(reg_family_display)
        if reg_family is None:
            drifts.append(
                f"{name}: unknown docs.family {reg_family_display!r} "
                "in models.json (not in _FAMILY_MAP)"
            )
        elif reg_family != req.family:
            drifts.append(
                f"{name}: family mismatch "
                f"(models.json {reg_family_display!r} -> {reg_family!r}, "
                f"router {req.family!r})"
            )

        # model_id
        if reg["model_id"] != req.model_id:
            drifts.append(
                f"{name}: model_id mismatch "
                f"(models.json {reg['model_id']!r}, "
                f"router {req.model_id!r})"
            )

        # reasoning_effort
        expected = _derive_reasoning_effort(
            name, reg.get("supports_codex_reasoning", False)
        )
        if expected != req.reasoning_effort:
            drifts.append(
                f"{name}: reasoning_effort mismatch "
                f"(expected {expected!r} from name + supports_codex_reasoning, "
                f"router {req.reasoning_effort!r})"
            )

    return drifts


# --- Tests ------------------------------------------------------------


class TestRegistryRouterConsistency:
    """Ensure router._SHORTHAND stays in sync with scripts/models.json."""

    def test_shorthand_key_sets_identical(self):
        """Every models.json model has a router entry and vice versa."""
        registry_models = _load_registry()
        registry_names = {m["name"] for m in registry_models}
        router_names = set(router._SHORTHAND.keys())

        only_registry = sorted(registry_names - router_names)
        only_router = sorted(router_names - registry_names)
        assert not only_registry, (
            "shorthands in models.json but missing from router._SHORTHAND: "
            + str(only_registry)
        )
        assert not only_router, (
            "shorthands in router._SHORTHAND but missing from models.json: "
            + str(only_router)
        )

    def test_family_agreement(self):
        """Family fields must agree between models.json and router."""
        registry_models = _load_registry()
        reg_by_name = {m["name"]: m for m in registry_models}

        mismatches: list[str] = []
        for name, req in router._SHORTHAND.items():
            reg = reg_by_name.get(name)
            if reg is None:
                continue  # key set test covers this
            reg_family = _FAMILY_MAP.get(reg["docs"]["family"])
            if reg_family != req.family:
                mismatches.append(
                    f"{name}: models.json family {reg['docs']['family']!r} "
                    f"-> {reg_family!r}, router {req.family!r}"
                )
        assert not mismatches, "Family mismatches:\n" + "\n".join(mismatches)

    def test_reasoning_effort_agreement(self):
        """reasoning_effort must match name suffix and supports_codex_reasoning."""
        registry_models = _load_registry()
        reg_by_name = {m["name"]: m for m in registry_models}

        mismatches: list[str] = []
        for name, req in router._SHORTHAND.items():
            reg = reg_by_name.get(name)
            if reg is None:
                continue
            expected = _derive_reasoning_effort(
                name, reg.get("supports_codex_reasoning", False)
            )
            if expected != req.reasoning_effort:
                mismatches.append(
                    f"{name}: expected {expected!r}, "
                    f"router {req.reasoning_effort!r}"
                )
        assert not mismatches, (
            "reasoning_effort mismatches:\n" + "\n".join(mismatches)
        )

    def test_model_id_agreement(self):
        """model_id must agree between models.json and router."""
        registry_models = _load_registry()
        reg_by_name = {m["name"]: m for m in registry_models}

        mismatches: list[str] = []
        for name, req in router._SHORTHAND.items():
            reg = reg_by_name.get(name)
            if reg is None:
                continue
            if reg["model_id"] != req.model_id:
                mismatches.append(
                    f"{name}: models.json {reg['model_id']!r}, "
                    f"router {req.model_id!r}"
                )
        assert not mismatches, (
            "model_id mismatches:\n" + "\n".join(mismatches)
        )

    def test_no_drift(self):
        """No drift should exist between models.json and router._SHORTHAND."""
        registry_models = _load_registry()
        drifts = _collect_drifts(registry_models, router._SHORTHAND)
        assert not drifts, (
            "Drift detected between models.json and router._SHORTHAND:\n"
            + "\n".join(drifts)
        )

    def test_flash_and_glm53_flash_are_identical_routes(self):
        """flash and glm53-flash must resolve identically to zai:glm-5.3-flash via opencode."""
        reg_by_name = {m["name"]: m for m in _load_registry()}

        for name in ("flash", "glm53-flash"):
            assert name in reg_by_name, f"{name} missing from models.json"
            entry = reg_by_name[name]
            assert entry["model_id"] == "zai:glm-5.3-flash", name
            assert entry["default_cli"] == "opencode", name
            assert entry["command"] == [
                "opencode",
                "run",
                "--format",
                "json",
                "-m",
                "zai/glm-5.3-flash",
                "--pure",
                "--agent",
                "build",
            ], name
            assert entry["routing"] == {
                "cli_overrides": ["opencode"],
                "force_direct_opencode": True,
                "google": False,
                "synthetic": False,
            }, name

        assert reg_by_name["glm53-flash"]["alias_of"] == "flash"
        assert reg_by_name["flash"]["model_id"] == reg_by_name["glm53-flash"]["model_id"]
        assert reg_by_name["flash"]["command"] == reg_by_name["glm53-flash"]["command"]
        assert reg_by_name["flash"]["routing"] == reg_by_name["glm53-flash"]["routing"]

        # Router entries agree and resolve identically.
        for name in ("flash", "glm53-flash"):
            req = router._SHORTHAND[name]
            assert req.family == "zai", name
            assert req.model_id == "zai:glm-5.3-flash", name
        assert router._SHORTHAND["flash"].model_id == router._SHORTHAND["glm53-flash"].model_id

    def test_glm53_still_targets_glm_5_3(self):
        """Adding GLM-5.3-Flash must not retarget glm5/glm53."""
        reg_by_name = {m["name"]: m for m in _load_registry()}
        for name in ("glm5", "glm53"):
            assert reg_by_name[name]["model_id"] == "zai:glm-5.3", name
            assert router._SHORTHAND[name].model_id == "zai:glm-5.3", name
        assert reg_by_name["glm52"]["model_id"] == "zai:glm-5.2"
        assert reg_by_name["zai"]["model_id"] == "zai:glm-4.7"
        assert reg_by_name["opencode"]["model_id"] == "zai:glm-4.7"
        assert reg_by_name["synthetic"]["model_id"] == "synthetic:syn:large:text"
        assert reg_by_name["syn-flash"]["model_id"] == "synthetic:syn:small:text"

    def test_syn_glm53_flash_routes_to_synthetic_provider(self):
        """syn-glm53-flash must route to Synthetic's hf:zai-org/GLM-5.3-Flash via opencode."""
        reg_by_name = {m["name"]: m for m in _load_registry()}
        assert "syn-glm53-flash" in reg_by_name
        entry = reg_by_name["syn-glm53-flash"]
        assert entry["model_id"] == "synthetic:hf:zai-org/GLM-5.3-Flash"
        assert entry["default_cli"] == "opencode"
        assert entry["supports_codex_reasoning"] is False
        assert entry["command"] == [
            "opencode",
            "run",
            "--format",
            "json",
            "-m",
            "synthetic/hf:zai-org/GLM-5.3-Flash",
            "--pure",
            "--agent",
            "build",
        ]
        assert entry["routing"] == {
            "cli_overrides": ["opencode"],
            "force_direct_opencode": True,
            "google": False,
            "synthetic": True,
        }
        assert entry["docs"]["family"] == "Synthetic"

        req = router._SHORTHAND["syn-glm53-flash"]
        assert req.family == "synthetic"
        assert req.model_id == "synthetic:hf:zai-org/GLM-5.3-Flash"
        assert req.force_cli == "opencode"
        assert req.strict_cli is True

        # Distinct from the Z.AI Coding Plan GLM-5.3-Flash shorthands.
        assert reg_by_name["flash"]["model_id"] == "zai:glm-5.3-flash"
        assert reg_by_name["glm53-flash"]["model_id"] == "zai:glm-5.3-flash"
        assert router._SHORTHAND["flash"].model_id == "zai:glm-5.3-flash"
        assert router._SHORTHAND["glm53-flash"].model_id == "zai:glm-5.3-flash"

        # Generic Synthetic defaults remain GLM-5.2 / GLM-4.7-Flash.
        assert reg_by_name["synthetic"]["model_id"] == "synthetic:syn:large:text"
        assert reg_by_name["syn-flash"]["model_id"] == "synthetic:syn:small:text"

    def test_syn_glm53_flash_resolves_strictly_to_opencode(self, monkeypatch):
        """Router resolution for syn-glm53-flash is strict-direct OpenCode."""
        fake = _FakeCache(
            {
                "clis": {
                    "codex": {"installed": True, "issues": []},
                    "opencode": {"installed": True, "issues": []},
                },
                "providers": {},
            }
        )
        monkeypatch.setattr(router, "load_cache_file", lambda: fake)

        cli, model_id, cmd = router.resolve_model("syn-glm53-flash")
        assert cli == "opencode"
        assert model_id == "synthetic:hf:zai-org/GLM-5.3-Flash"
        assert cmd == [
            "opencode",
            "run",
            "--format",
            "json",
            "-m",
            "synthetic/hf:zai-org/GLM-5.3-Flash",
            "--pure",
            "--agent",
            "build",
        ]

    def test_drift_missing_router_key_produces_actionable_message(self):
        """A model missing from router must produce a message naming it."""
        registry_models = _load_registry()
        modified = dict(router._SHORTHAND)
        del modified["codex"]

        drifts = _collect_drifts(registry_models, modified)
        assert len(drifts) >= 1
        assert any("codex" in d and "missing" in d for d in drifts), (
            f"Expected actionable message naming 'codex', got: {drifts}"
        )

    def test_drift_extra_router_key_produces_actionable_message(self):
        """An extra router entry must produce a message naming it."""
        registry_models = _load_registry()
        modified = dict(router._SHORTHAND)
        modified["bogus-model"] = router._ModelRequest(
            "bogus-model", family="openai"
        )

        drifts = _collect_drifts(registry_models, modified)
        assert len(drifts) >= 1
        assert any("bogus-model" in d and "missing" in d for d in drifts), (
            f"Expected actionable message naming 'bogus-model', got: {drifts}"
        )

    def test_drift_family_mismatch_produces_actionable_message(self):
        """A family mismatch must name the model and the field."""
        registry_models = _load_registry()
        modified = dict(router._SHORTHAND)
        modified["codex"] = replace(modified["codex"], family="zai")

        drifts = _collect_drifts(registry_models, modified)
        assert len(drifts) >= 1
        msg = drifts[0]
        assert "codex" in msg, f"Expected 'codex' in message: {msg}"
        assert "family" in msg, f"Expected 'family' in message: {msg}"

    def test_drift_reasoning_effort_produces_actionable_message(self):
        """A reasoning_effort mismatch must name the model and field."""
        registry_models = _load_registry()
        modified = dict(router._SHORTHAND)
        modified["codex-high"] = replace(
            modified["codex-high"], reasoning_effort=None
        )

        drifts = _collect_drifts(registry_models, modified)
        relevant = [d for d in drifts if "codex-high" in d]
        assert relevant, f"Expected message about 'codex-high', got: {drifts}"
        assert "reasoning_effort" in relevant[0], (
            f"Expected 'reasoning_effort' in message: {relevant[0]}"
        )

    def test_drift_model_id_produces_actionable_message(self):
        """A model_id mismatch must name the model and field."""
        registry_models = _load_registry()
        modified = dict(router._SHORTHAND)
        modified["gemini"] = replace(
            modified["gemini"], model_id="google:bogus-model"
        )

        drifts = _collect_drifts(registry_models, modified)
        relevant = [d for d in drifts if "gemini" in d and "model_id" in d]
        assert relevant, f"Expected message about 'gemini' model_id, got: {drifts}"
        assert "bogus-model" in relevant[0], (
            f"Expected 'bogus-model' in message: {relevant[0]}"
        )


# --- AGY map-divergence guard -----------------------------------------


class TestAGYMapConsistency:
    """Ensure the three copies of the AGY display-name map agree.

    router.py, plugins/agy.py, and prompt-executor/scripts/models.py each
    maintain their own copy of the AGY model-arg map.  These tests fail
    if any copy drifts, preventing silent wrong-display-name failures.
    """

    def test_agy_maps_are_identical(self):
        """All three _AGY_MODEL_ARGS dicts must contain the same entries."""
        # router.py
        router_map = dict(router._AGY_MODEL_ARGS)

        # plugins/agy.py — import through the plugins package (relative imports)
        from plugins import agy as agy_plugin  # noqa: E402
        plugin_map = dict(agy_plugin._AGY_MODEL_ARGS)

        # prompt-executor/scripts/models.py
        models_dir = _REPO_ROOT / "skills" / "prompt-executor" / "scripts"
        if str(models_dir) not in sys.path:
            sys.path.insert(0, str(models_dir))
        import models as models_mod  # noqa: E402
        executor_map = dict(models_mod._AGY_MODEL_ARGS)

        # All three complete maps must agree, including extra keys.
        assert router_map == plugin_map, (
            "router._AGY_MODEL_ARGS and plugins/agy.py._AGY_MODEL_ARGS differ:\n"
            f"  router only: {set(router_map.items()) - set(plugin_map.items())}\n"
            f"  plugin only: {set(plugin_map.items()) - set(router_map.items())}"
        )
        assert router_map == executor_map, (
            "router._AGY_MODEL_ARGS and prompt-executor models._AGY_MODEL_ARGS differ:\n"
            f"  router only: {set(router_map.items()) - set(executor_map.items())}\n"
            f"  executor only: {set(executor_map.items()) - set(router_map.items())}"
        )

    def test_gemini37_display_names_in_all_maps(self):
        """All three AGY maps must contain the gemini37 entries."""
        expected = {
            "google:gemini-3.7-flash": "Gemini 3.7 Flash (High)",
            "gemini": "Gemini 3.7 Flash (High)",
            "agy": "Gemini 3.7 Flash (High)",
            "gemini37": "Gemini 3.7 Flash (High)",
            "gemini37-high": "Gemini 3.7 Flash (High)",
            "gemini37-medium": "Gemini 3.7 Flash (Medium)",
            "gemini37-low": "Gemini 3.7 Flash (Low)",
        }

        # router.py
        for key, val in expected.items():
            assert key in router._AGY_MODEL_ARGS, f"router._AGY_MODEL_ARGS missing {key}"
            assert router._AGY_MODEL_ARGS[key] == val, (
                f"router._AGY_MODEL_ARGS[{key!r}] = {router._AGY_MODEL_ARGS[key]!r}, "
                f"expected {val!r}"
            )

        # plugins/agy.py — import through the plugins package (relative imports)
        from plugins import agy as agy_plugin  # noqa: E402
        for key, val in expected.items():
            assert key in agy_plugin._AGY_MODEL_ARGS, f"agy_plugin._AGY_MODEL_ARGS missing {key}"
            assert agy_plugin._AGY_MODEL_ARGS[key] == val, (
                f"agy_plugin._AGY_MODEL_ARGS[{key!r}] = {agy_plugin._AGY_MODEL_ARGS[key]!r}, "
                f"expected {val!r}"
            )

        # prompt-executor/scripts/models.py
        models_dir = _REPO_ROOT / "skills" / "prompt-executor" / "scripts"
        if str(models_dir) not in sys.path:
            sys.path.insert(0, str(models_dir))
        import models as models_mod  # noqa: E402
        for key, val in expected.items():
            assert models_mod._agy_model_arg(key) == val, (
                f"models._agy_model_arg({key!r}) = {models_mod._agy_model_arg(key)!r}, "
                f"expected {val!r}"
            )


    def test_gemini_agy_gemini37_share_registry_runtime(self):
        """`gemini`, `agy`, and `gemini37` are the same model and default command."""
        reg_by_name = {m["name"]: m for m in _load_registry()}
        entries = [reg_by_name[name] for name in ("gemini", "agy", "gemini37")]
        model_ids = {entry["model_id"] for entry in entries}
        assert model_ids == {"google:gemini-3.7-flash"}, model_ids
        default_clis = {entry["default_cli"] for entry in entries}
        assert default_clis == {"agy"}, default_clis
        commands = {tuple(entry["command"]) for entry in entries}
        assert commands == {
            (
                "agy",
                "--model",
                "Gemini 3.7 Flash (High)",
                "--dangerously-skip-permissions",
                "--print-timeout",
                "60m",
                "--output-format",
                "stream-json",
                "--print",
            )
        }, commands
        stdin_modes = {entry["stdin_mode"] for entry in entries}
        assert stdin_modes == {"arg"}, stdin_modes


# --- Fixture agreement (offline) -------------------------------------

_FIXTURE_PATH = Path(__file__).resolve().parent / "fixtures" / "agy-models.txt"


def _parse_fixture_display_names(path: Path) -> set[str]:
    """Parse display names from raw ``agy models`` output.

    Lines starting with '#' are comments. Blank lines are ignored. Current
    agy versions emit ``<model-id>\t<display-name>``; display-only fixtures
    remain supported for backwards compatibility.
    """
    if not path.exists():
        pytest.skip(f"Fixture not found: {path}")
    names: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        names.add(stripped.split("\t", 1)[-1])
    return names


class TestFixtureAgreement:
    """Verify daplug's agy display strings exist verbatim in the fixture.

    This test is purely offline (no network, no agy CLI).  It guards
    against typos in the display-name maps by checking every value in
    the AGY maps against the captured fixture.
    """

    def test_all_agy_display_names_in_fixture(self):
        """Every display name in router._AGY_MODEL_ARGS must appear in the fixture."""
        fixture_names = _parse_fixture_display_names(_FIXTURE_PATH)
        for key, display_name in router._AGY_MODEL_ARGS.items():
            assert display_name in fixture_names, (
                f"Display name {display_name!r} (for model_id {key!r}) "
                f"is not in the agy-models fixture"
            )

    def test_gemini37_display_names_in_fixture(self):
        """The three gemini37 display strings must be in the fixture."""
        fixture_names = _parse_fixture_display_names(_FIXTURE_PATH)
        assert "Gemini 3.7 Flash (Medium)" in fixture_names
        assert "Gemini 3.7 Flash (High)" in fixture_names
        assert "Gemini 3.7 Flash (Low)" in fixture_names


# --- Generated-file consistency --------------------------------------

class TestGeneratedFileConsistency:
    """Verify manage-models.py check exits 0 (generated docs in sync)."""

    def test_manage_models_check_exits_zero(self):
        """Run manage-models.py check and assert exit code 0."""
        repo_root = _REPO_ROOT
        script = repo_root / "scripts" / "manage-models.py"
        if not script.exists():
            pytest.skip("manage-models.py not found")
        result = subprocess.run(
            [sys.executable, str(script), "check"],
            capture_output=True,
            text=True,
            cwd=str(repo_root),
            timeout=30,
        )
        assert result.returncode == 0, (
            f"manage-models.py check exited {result.returncode}:\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )


# --- Optional live check ----------------------------------------------

@pytest.mark.skipif(
    not os.environ.get("DAPLUG_LIVE_AGY"),
    reason="Set DAPLUG_LIVE_AGY=1 to run live agy models verification",
)
class TestLiveAGYModels:
    """Optional live verification against real `agy models` output.

    Disabled by default (no network in CI).  Set DAPLUG_LIVE_AGY=1 to
    run locally after authenticating with agy.
    """

    def test_live_agy_display_names_match(self):
        """Every display name daplug sends must appear in live agy models."""
        result = subprocess.run(
            ["agy", "models"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            pytest.skip(f"agy models failed (rc={result.returncode}): {result.stderr}")
        live_names: set[str] = set()
        for line in result.stdout.splitlines():
            stripped = line.strip()
            if stripped:
                live_names.add(stripped.split("\t", 1)[-1])
        for key, display_name in router._AGY_MODEL_ARGS.items():
            assert display_name in live_names, (
                f"Display name {display_name!r} (for {key!r}) not found in "
                f"live `agy models` output"
            )
