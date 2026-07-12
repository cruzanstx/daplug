#!/usr/bin/env python3
"""Model registry loading and CLI command building for all supported models."""

import json
import os
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from paths import _read_config_value, get_repo_root

def _normalize_preferred_agent(value: Optional[str]) -> Optional[str]:
    v = (value or "").strip().lower()
    if not v:
        return None
    if v in {"claude-code", "claude_code"}:
        return "claude"
    if v.startswith("codex"):
        return "codex"
    if v in {"agy", "antigravity"}:
        return "agy"
    if v.startswith("gemini"):
        return "gemini"
    if v in {"qwen", "devstral", "local"}:
        return "opencode"
    return v


def _normalize_cli_override(value: Optional[str]) -> Optional[str]:
    v = (value or "").strip().lower()
    if not v:
        return None
    if v in {"cc", "claudecode"}:
        return "claude"
    if v == "antigravity":
        return "agy"
    return v


SUPPORTED_VARIANTS = ("none", "low", "medium", "high", "xhigh")
CODEX_REASONING_VARIANTS = {"high", "xhigh"}

MODEL_REGISTRY_PATH = Path(__file__).resolve().parents[3] / "scripts" / "models.json"


class ModelRegistryError(RuntimeError):
    """Raised when the model registry cannot be loaded."""


_REQUIRED_MODEL_FIELDS = {
    "name",
    "display",
    "model_id",
    "default_cli",
    "supports_codex_reasoning",
    "codex_profile",
    "claude_model_flag",
    "alias_of",
    "default_variant",
    "env",
    "stdin_mode",
    "command",
    "routing",
    "docs",
}


_RUNTIME_SPEC_FIELDS = (
    "model_id",
    "default_cli",
    "supports_codex_reasoning",
    "codex_profile",
    "claude_model_flag",
    "env",
    "stdin_mode",
    "command",
)

_ALLOWED_STDIN_MODES = {None, "dash", "arg", "stdin"}


def _load_model_registry(path: Optional[Path] = None) -> tuple[dict, dict[str, dict]]:
    """Load scripts/models.json relative to the plugin, not the current CWD."""
    registry_path = path or MODEL_REGISTRY_PATH
    if not registry_path.exists():
        raise ModelRegistryError(f"Model registry not found: {registry_path}")

    try:
        data = json.loads(registry_path.read_text())
    except json.JSONDecodeError as exc:
        raise ModelRegistryError(f"Model registry is invalid JSON: {registry_path}: {exc}") from exc
    except OSError as exc:
        raise ModelRegistryError(f"Model registry cannot be read: {registry_path}: {exc}") from exc

    if not isinstance(data, dict):
        raise ModelRegistryError(f"Model registry must be a JSON object: {registry_path}")
    if data.get("schema_version") != 1:
        raise ModelRegistryError(f"Unsupported model registry schema_version in {registry_path}")
    models = data.get("models")
    if not isinstance(models, list) or not models:
        raise ModelRegistryError(f"Model registry must contain a non-empty models list: {registry_path}")

    by_name: dict[str, dict] = {}
    for index, model in enumerate(models):
        if not isinstance(model, dict):
            raise ModelRegistryError(f"Model registry entry #{index + 1} must be an object")
        missing = sorted(_REQUIRED_MODEL_FIELDS - set(model))
        if missing:
            name = model.get("name", f"#{index + 1}")
            raise ModelRegistryError(f"Model registry entry {name} missing fields: {', '.join(missing)}")
        name = model.get("name")
        if not isinstance(name, str) or not name:
            raise ModelRegistryError(f"Model registry entry #{index + 1} has invalid name")
        if name in by_name:
            raise ModelRegistryError(f"Duplicate model registry entry: {name}")
        command = model.get("command")
        if not isinstance(command, list) or not all(isinstance(item, str) for item in command):
            raise ModelRegistryError(f"Model registry entry {name} command must be a list of strings")
        env = model.get("env")
        if not isinstance(env, dict) or not all(isinstance(key, str) and isinstance(value, str) for key, value in env.items()):
            raise ModelRegistryError(f"Model registry entry {name} env must be a string map")
        if model.get("stdin_mode") not in _ALLOWED_STDIN_MODES:
            raise ModelRegistryError(f"Model registry entry {name} has invalid stdin_mode")
        routing = model.get("routing")
        if not isinstance(routing, dict):
            raise ModelRegistryError(f"Model registry entry {name} has invalid routing")
        docs = model.get("docs")
        if not isinstance(docs, dict):
            raise ModelRegistryError(f"Model registry entry {name} has invalid docs metadata")
        by_name[name] = model

    for name, model in by_name.items():
        alias_of = model.get("alias_of")
        if alias_of is not None and alias_of not in by_name:
            raise ModelRegistryError(f"Model registry entry {name} aliases unknown model: {alias_of}")

    return data, by_name


MODEL_REGISTRY, MODEL_REGISTRY_BY_NAME = _load_model_registry()
MODEL_CHOICES = tuple(MODEL_REGISTRY_BY_NAME.keys())

MODEL_ALIAS_BASE = {
    name: str(model["alias_of"])
    for name, model in MODEL_REGISTRY_BY_NAME.items()
    if model.get("alias_of")
}

MODEL_ALIAS_DEFAULT_VARIANT = {
    name: str(model["default_variant"])
    for name, model in MODEL_REGISTRY_BY_NAME.items()
    if model.get("default_variant")
}

LEGACY_MODEL_DISPLAY = {
    name: str(model["display"])
    for name, model in MODEL_REGISTRY_BY_NAME.items()
}

MODEL_SPECS = {
    name: {field: model[field] for field in _RUNTIME_SPEC_FIELDS}
    for name, model in MODEL_REGISTRY_BY_NAME.items()
    if not model.get("alias_of")
}

SYNTHETIC_MODEL_SHORTHANDS = {
    name
    for name, model in MODEL_REGISTRY_BY_NAME.items()
    if model.get("routing", {}).get("synthetic")
}

GOOGLE_MODEL_SHORTHANDS = {
    name
    for name, model in MODEL_REGISTRY_BY_NAME.items()
    if model.get("routing", {}).get("google")
}

CLI_OVERRIDE_SUPPORTED_MODELS: dict[str, set[str]] = {}
for _model_name, _model in MODEL_REGISTRY_BY_NAME.items():
    for _cli in _model.get("routing", {}).get("cli_overrides", []):
        CLI_OVERRIDE_SUPPORTED_MODELS.setdefault(str(_cli), set()).add(_model_name)

FORCE_DIRECT_OPENCODE_MODELS = {
    name
    for name, model in MODEL_REGISTRY_BY_NAME.items()
    if model.get("routing", {}).get("force_direct_opencode")
}


@dataclass(frozen=True)
class _ExecutionConfig:
    requested_model: str
    base_model: str
    selected_cli: str
    model_id: str
    variant: Optional[str]
    command: list[str]
    env: dict[str, str]
    stdin_mode: Optional[str]
    display: str


def _normalize_variant(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    v = value.strip().lower()
    if not v:
        return None
    if v not in SUPPORTED_VARIANTS:
        allowed = ", ".join(SUPPORTED_VARIANTS)
        raise ValueError(f"Unsupported --variant '{value}'. Supported values: {allowed}")
    if v == "none":
        return None
    return v


def _canonical_model(model: str) -> str:
    return MODEL_ALIAS_BASE.get(model, model)


def _strip_provider_prefix(model_id: str) -> str:
    return model_id.split(":", 1)[1] if ":" in model_id else model_id


def _agy_model_arg(model_id: str) -> str:
    agy_args = {
        "google:gemini-3-flash-preview": "Gemini 3.5 Flash (Medium)",
        "google:gemini-3.5-flash": "Gemini 3.5 Flash (Medium)",
        "google:gemini-2.5-flash": "Gemini 3.5 Flash (Medium)",
        "google:gemini-2.5-flash-lite": "Gemini 3.5 Flash (Low)",
        "google:gemini-2.5-pro": "Gemini 3.1 Pro (High)",
        "google:gemini-3-pro-preview": "Gemini 3.1 Pro (High)",
        "google:gemini-3.1-pro-preview": "Gemini 3.1 Pro (High)",
    }
    return agy_args.get(model_id, model_id)


def _opencode_model_spec(model_id: str) -> str:
    if model_id.startswith("local:"):
        rest = model_id.split(":", 1)[1]
        if ":" in rest:
            provider, model = rest.split(":", 1)
            return f"{provider}/{model}"
        return rest
    if ":" not in model_id:
        return model_id
    provider, rest = model_id.split(":", 1)
    return f"{provider}/{rest}"


def _claude_cli_command(model_flag: Optional[str] = None) -> list[str]:
    cmd = [
        "claude",
        "--print",
        "--no-session-persistence",
        "--output-format",
        "text",
        "--input-format",
        "text",
        "--permission-mode",
        "dontAsk",
    ]
    if model_flag:
        cmd.extend(["--model", model_flag])
    return cmd


def apply_claude_sandbox_permissions(
    command: Optional[list[str]],
    *,
    sandbox_active: bool,
    allow_bypass_without_sandbox: bool = False,
) -> Optional[list[str]]:
    """Escalate Claude's headless permission mode when a filesystem boundary exists.

    Headless Claude runs with ``--permission-mode dontAsk``, which cannot prompt
    for approval and therefore denies Write/Edit/Bash — the model can read but
    not implement. When an external Bubblewrap sandbox is the filesystem
    boundary, switch to ``bypassPermissions`` so the task can actually run;
    bwrap still confines writes to the worktree. Without a sandbox, only
    escalate when the caller explicitly opts into the unsafe bypass.

    Returns the command unchanged for non-Claude commands or when no escalation
    applies, so it is safe to call unconditionally.
    """
    if not command or Path(command[0]).name != "claude":
        return command
    try:
        idx = command.index("--permission-mode")
    except ValueError:
        return command
    if idx + 1 >= len(command) or command[idx + 1] != "dontAsk":
        return command
    if not (sandbox_active or allow_bypass_without_sandbox):
        return command
    updated = list(command)
    updated[idx + 1] = "bypassPermissions"
    return updated


def _require_claude_cli() -> None:
    if shutil.which("claude"):
        return
    raise RuntimeError(
        "Claude Code CLI ('claude') not found in PATH.\n"
        "Install Claude Code and run `/daplug:detect-clis` to refresh daplug's CLI cache."
    )


def _validate_cli_override(model: str, cli_override: Optional[str]) -> None:
    if not cli_override:
        return
    supported = CLI_OVERRIDE_SUPPORTED_MODELS.get(cli_override, set())
    if model in supported:
        return
    supported_models = ", ".join(sorted(supported))
    raise ValueError(
        f"--cli {cli_override} is not supported with --model {model}.\n"
        f"Supported models for --cli {cli_override}: {supported_models}"
    )


def _resolve_router_command(
    repo_root: Path,
    model: str,
    preferred_cli: Optional[str],
) -> Optional[tuple[str, str, list[str]]]:
    try:
        router_dir = repo_root / "skills" / "cli-detector" / "scripts"
        if not router_dir.exists():
            return None
        if str(router_dir) not in sys.path:
            sys.path.append(str(router_dir))
        import router  # type: ignore

        cli_name, model_id, cmd = router.resolve_model(model, preferred_cli=preferred_cli)
        return ((cli_name or "").strip().lower(), str(model_id), list(cmd))
    except Exception:
        return None


def _build_codex_command(
    model: str,
    model_spec: dict,
    model_id: str,
    variant: Optional[str],
) -> list[str]:
    cmd = ["codex", "exec", "--full-auto"]
    profile = model_spec.get("codex_profile")
    if profile:
        cmd.extend(["--profile", str(profile)])
    else:
        stripped = _strip_provider_prefix(model_id)
        if stripped and stripped != "gpt-5.5":
            cmd.extend(["-m", stripped])

    if variant:
        if variant not in CODEX_REASONING_VARIANTS:
            raise ValueError(
                f"--variant {variant} is not supported with Codex for --model {model}. "
                "Codex supports high/xhigh only. Use --cli opencode for low/medium variants."
            )
        if not model_spec.get("supports_codex_reasoning"):
            raise ValueError(
                f"--variant {variant} is not supported with --model {model} when using Codex."
            )
        cmd.extend(["-c", f'model_reasoning_effort="{variant}"'])
    return cmd


def _build_opencode_command(model_id: str, variant: Optional[str]) -> list[str]:
    cmd = ["opencode", "run", "--format", "json", "-m", _opencode_model_spec(model_id)]
    if variant:
        cmd.extend(["--variant", variant])
    return cmd


def _build_agy_command(model: str, model_id: str, variant: Optional[str]) -> list[str]:
    if variant:
        raise ValueError(
            f"--variant {variant} is not supported with --model {model} when using Antigravity."
        )
    # agy --print requires its prompt as an argv value; stdin leaves --print without an argument.
    return ["agy", "--model", _agy_model_arg(model_id), "--print"]


def _build_gemini_command(model: str, model_id: str, variant: Optional[str]) -> list[str]:
    if variant:
        raise ValueError(
            f"--variant {variant} is not supported with --model {model} when using Gemini."
        )
    return ["gemini", "-y", "-m", _strip_provider_prefix(model_id), "-p"]


def _build_claude_command(model: str, model_spec: dict, variant: Optional[str]) -> list[str]:
    if variant:
        raise ValueError(
            f"--variant {variant} is not supported with --model {model} when using Claude Code CLI."
        )
    return _claude_cli_command(model_spec.get("claude_model_flag"))


def _require_synthetic_api_key(model: str, model_id: str) -> None:
    if model not in SYNTHETIC_MODEL_SHORTHANDS and not model_id.startswith("synthetic:"):
        return
    if os.environ.get("SYNTHETIC_API_KEY"):
        return
    raise RuntimeError(
        "SYNTHETIC_API_KEY is required for Synthetic models. "
        "Create a key at https://synthetic.new/dashboard and export it before using "
        "--model synthetic, syn-flash, syn-kimi, or syn-qwen."
    )


def _env_for_command(selected_cli: str, command: list[str]) -> dict[str, str]:
    env: dict[str, str] = {}
    if selected_cli == "codex" and "--profile" in command:
        try:
            profile = command[command.index("--profile") + 1]
            if str(profile).startswith("local"):
                env["LMSTUDIO_API_KEY"] = "lm-studio"
        except (ValueError, IndexError):
            pass
    return env


def _registry_runtime(model_spec: dict) -> tuple[list[str], dict[str, str], Optional[str]]:
    return (
        list(model_spec["command"]),
        dict(model_spec["env"]),
        model_spec["stdin_mode"],
    )


def _dynamic_display(model: str, selected_cli: str, model_id: str, variant: Optional[str]) -> str:
    cli_label = {
        "codex": "Codex",
        "opencode": "OpenCode",
        "agy": "Antigravity",
        "gemini": "Gemini",
        "claude": "Claude Code",
    }.get(selected_cli, selected_cli)
    if selected_cli == "opencode":
        target = _opencode_model_spec(model_id)
    else:
        target = _strip_provider_prefix(model_id)
    suffix = f", variant={variant}" if variant else ""
    return f"{model} ({target} via {cli_label}{suffix})"


def _cli_info_from_router(cli_name: str, model_id: str, cmd: list[str]) -> dict:
    cli = (cli_name or "").strip().lower()
    if cli == "claude":
        return {
            "command": cmd,
            "display": f"claude ({model_id})",
            "env": {},
            # Claude Code reads prompt content from stdin in --print mode.
            "stdin_mode": "stdin",
        }

    if cli == "codex":
        stdin_mode = "dash"
    else:
        stdin_mode = "arg"

    env: dict = {}
    if cli == "codex" and "--profile" in cmd:
        try:
            profile = cmd[cmd.index("--profile") + 1]
            if str(profile).startswith("local"):
                # Keep backwards compatibility with existing local profiles.
                env["LMSTUDIO_API_KEY"] = "lm-studio"
        except (ValueError, IndexError):
            pass

    return {
        "command": cmd,
        "display": f"{cli} ({model_id})",
        "env": env,
        "stdin_mode": stdin_mode,
    }


def get_cli_info(
    model: str,
    repo_root: Optional[Path] = None,
    cli_override: Optional[str] = None,
    variant: Optional[str] = None,
) -> dict:
    """Get CLI command and info for a model.

    stdin_mode: How to pass prompt content
      - "dash": Use '-' as last arg, pipe content to stdin (codex)
      - "arg": Pass content as command line argument (agy/gemini/opencode)
      - "stdin": Pipe content to stdin (claude --print)
      - None: Handled by Task subagent (claude)
    """
    cli_override = _normalize_cli_override(cli_override)
    explicit_variant = variant is not None
    explicit_variant_value = _normalize_variant(variant)
    effective_variant = (
        explicit_variant_value
        if explicit_variant
        else MODEL_ALIAS_DEFAULT_VARIANT.get(model)
    )

    _validate_cli_override(model, cli_override)

    base_model = _canonical_model(model)
    requested_model_spec = MODEL_REGISTRY_BY_NAME.get(model)
    model_spec = MODEL_SPECS.get(base_model)
    if requested_model_spec is None or model_spec is None:
        raise ValueError(f"Unknown model shorthand: {model}")

    if model == "claude" and cli_override is None:
        if effective_variant:
            raise ValueError(
                f"--variant {effective_variant} is not supported with --model claude Task subagent mode."
            )
        return {
            "command": [],
            "display": LEGACY_MODEL_DISPLAY["claude"],
            "env": dict(requested_model_spec["env"]),
            "stdin_mode": requested_model_spec["stdin_mode"],
            "selected_cli": "subagent",
            "base_model": base_model,
            "model_id": model_spec["model_id"],
            "variant": None,
        }

    repo_root = repo_root or get_repo_root()
    preferred = cli_override or _normalize_preferred_agent(_read_config_value(repo_root, "preferred_agent"))

    # Preserve direct OpenCode defaults for shortcuts whose model specs are tied
    # to OpenCode-compatible provider refs instead of preferred-agent routing.
    force_direct_opencode = model in FORCE_DIRECT_OPENCODE_MODELS and cli_override is None

    selected_cli = cli_override or requested_model_spec["default_cli"]
    model_id = str(requested_model_spec["model_id"])
    router_command: Optional[list[str]] = None

    router_resolution = None if force_direct_opencode else _resolve_router_command(repo_root, model, preferred)
    if router_resolution:
        router_cli, router_model_id, router_cmd = router_resolution
        if not cli_override:
            selected_cli = router_cli
        if router_model_id:
            model_id = router_model_id
        router_command = router_cmd

    if selected_cli == "claude":
        _require_claude_cli()

    _require_synthetic_api_key(model, model_id)

    use_registry_runtime = (
        router_resolution is None
        and cli_override is None
        and not explicit_variant
        and selected_cli == requested_model_spec["default_cli"]
    )

    if use_registry_runtime:
        command, env, stdin_mode = _registry_runtime(requested_model_spec)
    elif selected_cli == "codex":
        command = _build_codex_command(model, model_spec, model_id, effective_variant)
        env = _env_for_command(selected_cli, command)
        stdin_mode = "dash"
    elif selected_cli == "opencode":
        command = _build_opencode_command(model_id, effective_variant)
        env = _env_for_command(selected_cli, command)
        stdin_mode = "arg"
    elif selected_cli == "agy":
        command = _build_agy_command(model, model_id, effective_variant)
        env = _env_for_command(selected_cli, command)
        stdin_mode = "arg"
    elif selected_cli == "gemini":
        command = _build_gemini_command(model, model_id, effective_variant)
        env = _env_for_command(selected_cli, command)
        stdin_mode = "arg"
    elif selected_cli == "claude":
        # Keep default claude model unpinned unless a cc-* alias selected a concrete flag.
        if router_command and model in {"cc-sonnet", "cc-opus"} and cli_override is None and not explicit_variant:
            command = router_command
        elif model == "claude":
            command = _build_claude_command(model, {**model_spec, "claude_model_flag": None}, effective_variant)
        else:
            command = _build_claude_command(model, model_spec, effective_variant)
        env = _env_for_command(selected_cli, command)
        stdin_mode = "stdin"
    else:
        # Preserve compatibility with router-only CLIs (for example aider) when no
        # explicit --cli override is requested.
        if router_command is None:
            raise ValueError(f"Unsupported CLI selected for --model {model}: {selected_cli}")
        if effective_variant:
            raise ValueError(
                f"--variant {effective_variant} is not supported when router selects CLI '{selected_cli}'. "
                "Use --cli codex or --cli opencode."
            )
        info = _cli_info_from_router(selected_cli, model_id, router_command)
        info.update({
            "selected_cli": selected_cli,
            "base_model": base_model,
            "model_id": model_id,
            "variant": None,
        })
        return info

    display = LEGACY_MODEL_DISPLAY.get(model, _dynamic_display(model, selected_cli, model_id, effective_variant))
    if cli_override or explicit_variant or selected_cli != model_spec["default_cli"]:
        display = _dynamic_display(model, selected_cli, model_id, effective_variant)

    config = _ExecutionConfig(
        requested_model=model,
        base_model=base_model,
        selected_cli=selected_cli,
        model_id=model_id,
        variant=effective_variant,
        command=command,
        env=env,
        stdin_mode=stdin_mode,
        display=display,
    )

    return {
        "command": config.command,
        "display": config.display,
        "env": config.env,
        "stdin_mode": config.stdin_mode,
        "selected_cli": config.selected_cli,
        "base_model": config.base_model,
        "model_id": config.model_id,
        "variant": config.variant,
    }
