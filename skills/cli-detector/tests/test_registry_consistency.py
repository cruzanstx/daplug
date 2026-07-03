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
