"""
Model routing based on CLI detection cache.

Responsibilities:
- Load and validate the CLI cache
- Resolve model shorthand to actual CLI + model
- Provide fallback chain when preferred CLI unavailable
- Handle local model routing (LM Studio / Ollama / vLLM)
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from cache import default_cache_path, load_cache_file


class ModelNotAvailable(RuntimeError):
    """Raised when no installed CLI can satisfy a model request."""


@dataclass(frozen=True)
class _ModelRequest:
    shorthand: str
    family: str  # "openai" | "anthropic" | "google" | "zai" | "local"
    model_id: Optional[str] = None
    reasoning_effort: Optional[str] = None  # "high" | "xhigh"
    force_cli: Optional[str] = None
    strict_cli: bool = False
    local_hint: Optional[str] = None
    codex_profile: Optional[str] = None


_SHORTHAND: dict[str, _ModelRequest] = {
    # OpenAI (Codex CLI)
    "codex": _ModelRequest("codex", family="openai", model_id="openai:gpt-5.3-codex"),
    "codex-high": _ModelRequest(
        "codex-high",
        family="openai",
        model_id="openai:gpt-5.3-codex",
        reasoning_effort="high",
    ),
    "codex-xhigh": _ModelRequest(
        "codex-xhigh",
        family="openai",
        model_id="openai:gpt-5.3-codex",
        reasoning_effort="xhigh",
    ),
    "gpt52": _ModelRequest("gpt52", family="openai", model_id="openai:gpt-5.2"),
    "gpt52-high": _ModelRequest(
        "gpt52-high",
        family="openai",
        model_id="openai:gpt-5.2",
        reasoning_effort="high",
    ),
    "gpt52-xhigh": _ModelRequest(
        "gpt52-xhigh",
        family="openai",
        model_id="openai:gpt-5.2",
        reasoning_effort="xhigh",
    ),
    # Google (Gemini CLI)
    # Keep preview shorthands for backwards compatibility; availability depends on user auth/plan.
    "gemini": _ModelRequest("gemini", family="google", model_id="google:gemini-3-flash-preview"),
    "gemini-high": _ModelRequest("gemini-high", family="google", model_id="google:gemini-2.5-pro"),
    "gemini-xhigh": _ModelRequest("gemini-xhigh", family="google", model_id="google:gemini-3-pro-preview"),
    "gemini25pro": _ModelRequest("gemini25pro", family="google", model_id="google:gemini-2.5-pro"),
    "gemini25flash": _ModelRequest("gemini25flash", family="google", model_id="google:gemini-2.5-flash"),
    "gemini25lite": _ModelRequest("gemini25lite", family="google", model_id="google:gemini-2.5-flash-lite"),
    "gemini3flash": _ModelRequest("gemini3flash", family="google", model_id="google:gemini-3-flash-preview"),
    "gemini3pro": _ModelRequest("gemini3pro", family="google", model_id="google:gemini-3-pro-preview"),
    # Z.AI
    "zai": _ModelRequest("zai", family="zai", model_id="zai:glm-4.7"),
    "opencode": _ModelRequest(
        "opencode",
        family="zai",
        model_id="zai:glm-4.7",
        force_cli="opencode",
        strict_cli=True,
    ),
    # Local models (provider is detected at runtime)
    "local": _ModelRequest(
        "local",
        family="local",
        model_id="lmstudio:qwen3-next-80b",
        force_cli="opencode",
    ),
    "qwen": _ModelRequest(
        "qwen",
        family="local",
        model_id="lmstudio:qwen3-next-80b",
        local_hint="qwen",
        force_cli="opencode",
        codex_profile="local",
    ),
    "devstral": _ModelRequest(
        "devstral",
        family="local",
        model_id="lmstudio:devstral-small-2-2512",
        local_hint="devstral",
        force_cli="opencode",
        codex_profile="local-devstral",
    ),
    # Claude (subagent path; no external command)
    "claude": _ModelRequest("claude", family="anthropic", model_id="anthropic:claude", force_cli="claude"),
}

_ALIASES: dict[str, str] = {
    "gpt-5.2": "gpt52",
    "gpt5.2": "gpt52",
    "gpt-5.2-high": "gpt52-high",
    "gpt-5.2-xhigh": "gpt52-xhigh",
}

_FALLBACK_CHAINS: dict[str, list[str]] = {
    "anthropic": ["claude", "opencode", "aider"],
    "openai": ["codex", "opencode", "aider"],
    "google": ["gemini", "opencode", "aider"],
    "zai": ["opencode", "codex"],
    "local": ["opencode", "codex"],
}


def _normalize_shorthand(value: str) -> str:
    s = (value or "").strip().lower()
    return _ALIASES.get(s, s)


def _model_provider(model_id: Optional[str]) -> str:
    if not model_id:
        return ""
    if ":" not in model_id:
        return ""
    return model_id.split(":", 1)[0].strip().lower()


def _strip_provider_prefix(model_id: str) -> str:
    return model_id.split(":", 1)[1] if ":" in model_id else model_id


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


def _is_embedding_model(name: str) -> bool:
    """Check if model name suggests it's an embedding model (not for chat/instruct)."""
    lower = name.lower()
    # Common embedding model indicators
    embedding_keywords = ["embed", "embedding", "arctic-embed", "nomic-embed", "bge-", "e5-"]
    # Other non-instruct model types
    other_keywords = ["whisper", "tts", "speech", "vision-only", "rerank"]
    for kw in embedding_keywords + other_keywords:
        if kw in lower:
            return True
    return False


def _pick_best_default_model(models: list[str]) -> Optional[str]:
    """Pick the best default model, preferring instruct/chat models over embeddings."""
    if not models:
        return None

    # Filter out embedding and other non-chat models
    chat_models = [m for m in models if not _is_embedding_model(m)]

    if chat_models:
        # Prefer larger models first, then instruct/chat/coder variants
        for keyword in ["120b", "80b", "70b", "32b", "30b", "20b", "8b", "coder", "instruct", "chat"]:
            for m in chat_models:
                if keyword in m.lower():
                    return m
        return chat_models[0]

    # Fallback to first model if all are embeddings
    return models[0]


def _match_model_hint(hint: Optional[str], models: list[str]) -> Optional[str]:
    if not models:
        return None
    if not hint:
        return _pick_best_default_model(models)
    target = hint.strip().lower()
    for m in models:
        if target in str(m).lower():
            return str(m)
    return _pick_best_default_model(models)


def _cli_has_error_issues(cli_info: dict[str, Any]) -> bool:
    issues = cli_info.get("issues") or []
    if not isinstance(issues, list):
        return False
    for issue in issues:
        if not isinstance(issue, dict):
            continue
        if str(issue.get("severity") or "").lower() == "error":
            return True
    return False


def _choose_cli(
    cache: dict[str, Any],
    family: str,
    preferred_cli: Optional[str],
    forced_cli: Optional[str] = None,
) -> str:
    clis = cache.get("clis") or {}
    if not isinstance(clis, dict):
        clis = {}

    chain = list(_FALLBACK_CHAINS.get(family, []))
    if forced_cli:
        chain = [forced_cli] + [c for c in chain if c != forced_cli]

    pref = (preferred_cli or "").strip().lower() if preferred_cli else ""
    if pref:
        if pref in chain:
            chain = [pref] + [c for c in chain if c != pref]
        else:
            # If preferred is installed, try it first (best-effort).
            pref_info = clis.get(pref) if isinstance(clis, dict) else None
            if isinstance(pref_info, dict) and pref_info.get("installed"):
                chain = [pref] + chain

    # Prefer installed + no error issues.
    for name in chain:
        info = clis.get(name)
        if not isinstance(info, dict) or not info.get("installed"):
            continue
        if _cli_has_error_issues(info):
            continue
        return name

    # Fall back to installed even if issues exist.
    for name in chain:
        info = clis.get(name)
        if isinstance(info, dict) and info.get("installed"):
            return name

    raise ModelNotAvailable(
        "No installed CLI can satisfy this request.\n"
        "Run `/detect-clis` to refresh the cache, or install a supported CLI.\n"
        f"Expected one of: {', '.join(chain) if chain else '(none)'}."
    )


def get_available_models() -> list[dict]:
    """Return all models available across installed CLIs."""
    cache_obj = load_cache_file()
    if cache_obj is None:
        return []
    cache = cache_obj.to_dict()
    clis = cache.get("clis") or {}
    if not isinstance(clis, dict):
        return []

    models: list[dict] = []
    for cli_name, info in clis.items():
        if not isinstance(info, dict) or not info.get("installed"):
            continue
        for model in info.get("models") or []:
            if not isinstance(model, dict):
                continue
            item = dict(model)
            item.setdefault("cli", cli_name)
            models.append(item)
    return models


def _resolve_local_model(
    cache: dict[str, Any],
    model_hint: Optional[str],
    preferred_cli: Optional[str],
    request: _ModelRequest,
) -> tuple[str, str, list[str]]:
    def _requested_model(provider: str) -> Optional[str]:
        if not request.model_id:
            return None
        if ":" not in request.model_id:
            return None
        req_provider = _model_provider(request.model_id)
        if req_provider != provider:
            return None
        return _strip_provider_prefix(request.model_id)

    providers = cache.get("providers") or {}
    if not isinstance(providers, dict):
        providers = {}

    lmstudio = providers.get("lmstudio") if isinstance(providers.get("lmstudio"), dict) else {}
    ollama = providers.get("ollama") if isinstance(providers.get("ollama"), dict) else {}
    vllm = providers.get("vllm") if isinstance(providers.get("vllm"), dict) else {}

    if isinstance(lmstudio, dict) and lmstudio.get("running"):
        loaded = lmstudio.get("loaded_models") if isinstance(lmstudio.get("loaded_models"), list) else []
        requested = _requested_model("lmstudio")
        selected = requested or _match_model_hint(model_hint, [str(x) for x in loaded if x])
        model_id = f"local:lmstudio:{selected}" if selected else "local:lmstudio"
        cli = _choose_cli(
            cache,
            family="local",
            preferred_cli=preferred_cli,
            forced_cli=request.force_cli,
        )
        cmd = _build_command(cli, model_id, request)
        return cli, model_id, cmd

    if isinstance(vllm, dict) and vllm.get("running"):
        loaded = vllm.get("loaded_models") if isinstance(vllm.get("loaded_models"), list) else []
        requested = _requested_model("vllm")
        selected = requested or _match_model_hint(model_hint, [str(x) for x in loaded if x])
        model_id = f"local:vllm:{selected}" if selected else "local:vllm"
        cli = _choose_cli(
            cache,
            family="local",
            preferred_cli=preferred_cli,
            forced_cli=request.force_cli,
        )
        cmd = _build_command(cli, model_id, request)
        return cli, model_id, cmd

    if isinstance(ollama, dict) and ollama.get("running"):
        loaded = ollama.get("loaded_models") if isinstance(ollama.get("loaded_models"), list) else []
        requested = _requested_model("ollama")
        selected = requested or _match_model_hint(model_hint, [str(x) for x in loaded if x])
        model_id = f"local:ollama:{selected}" if selected else "local:ollama"
        cli = _choose_cli(
            cache,
            family="local",
            preferred_cli=preferred_cli,
            forced_cli=request.force_cli,
        )
        cmd = _build_command(cli, model_id, request)
        return cli, model_id, cmd

    raise ModelNotAvailable(
        "No local model provider detected.\n"
        "Start LM Studio / Ollama / vLLM locally, or configure remote endpoints in <daplug_config>:\n"
        "  <daplug_config>\n"
        "  local_providers:\n"
        "    lmstudio: http://your-server:1234/v1\n"
        "    ollama: http://your-server:11434/v1\n"
        "    vllm: http://your-server:8000/v1\n"
        "  </daplug_config>"
    )


def _build_command(cli: str, model_id: str, request: _ModelRequest) -> list[str]:
    cli = cli.strip().lower()

    # Claude is handled by the /run-prompt Task subagent path; no external command.
    if cli == "claude":
        return []

    if cli == "codex":
        cmd: list[str] = ["codex", "exec", "--full-auto"]

        if request.family == "zai":
            # Existing daplug convention: codex profile "zai" points at Z.AI.
            cmd.extend(["--profile", "zai"])
        elif request.family == "local":
            profile = request.codex_profile or "local"
            cmd.extend(["--profile", profile])
        else:
            cmd.extend(["-m", _strip_provider_prefix(model_id)])

        if request.reasoning_effort:
            cmd.extend(["-c", f'model_reasoning_effort="{request.reasoning_effort}"'])

        return cmd

    if cli == "gemini":
        cmd = ["gemini", "-y", "-m", _strip_provider_prefix(model_id), "-p"]
        return cmd

    if cli == "opencode":
        cmd = ["opencode", "run", "--format", "json", "-m", _opencode_model_spec(model_id)]
        return cmd

    if cli == "aider":
        model = _strip_provider_prefix(model_id)
        # For ollama, aider prefers the explicit "ollama/<model>" format.
        if _model_provider(model_id) in {"ollama"}:
            model = _opencode_model_spec(model_id)
        cmd = ["aider", "--yes", "--model", model, "--message"]
        return cmd

    # Unknown CLI name; treat as not routable.
    raise ModelNotAvailable(f"Unknown CLI runner: {cli}")


def resolve_model(shorthand: str, preferred_cli: str | None = None) -> tuple[str, str, list[str]]:
    """
    Resolve model shorthand to (cli_name, model_id, command_args).

    Args:
        shorthand: User input like "codex", "gemini-high", "local", "gpt52"
        preferred_cli: From daplug_config preferred_agent

    Returns:
        (cli_name, model_id, command_args)

    Raises:
        ModelNotAvailable: If no installed CLI can run the requested model
    """
    norm = _normalize_shorthand(shorthand)
    request = _SHORTHAND.get(norm)

    if request is None:
        # Accept normalized model IDs directly (e.g., "openai:gpt-5.2").
        if ":" in norm:
            provider = _model_provider(norm)
            family = (
                "openai"
                if provider == "openai"
                else "anthropic"
                if provider == "anthropic"
                else "google"
                if provider == "google"
                else "zai"
                if provider == "zai"
                else "local"
                if provider in {"local", "ollama", "lmstudio"}
                else provider or "openai"
            )
            request = _ModelRequest(shorthand=norm, family=family, model_id=norm)
        else:
            raise ModelNotAvailable(f"Unknown model shorthand: {shorthand}")

    cache_obj = load_cache_file()
    if cache_obj is None:
        raise ModelNotAvailable(
            "CLI detection cache not found.\n"
            f"Expected at {default_cache_path()}.\n"
            "Run `/detect-clis` to generate the cache."
        )
    cache = cache_obj.to_dict()

    if request.family == "local":
        hint = request.local_hint or (norm if norm not in {"local"} else None)
        return _resolve_local_model(cache, hint, preferred_cli, request)

    model_id = request.model_id or norm
    if request.force_cli and request.strict_cli:
        clis = cache.get("clis") or {}
        info = clis.get(request.force_cli) if isinstance(clis, dict) else None
        if not isinstance(info, dict) or not info.get("installed"):
            raise ModelNotAvailable(
                f"Requested CLI '{request.force_cli}' is not installed.\n"
                "Install it, or use a family shorthand (e.g., 'zai') to allow fallbacks."
            )
        cli = request.force_cli
    else:
        cli = _choose_cli(cache, family=request.family, preferred_cli=preferred_cli, forced_cli=request.force_cli)
    cmd = _build_command(cli, model_id, request)
    return cli, model_id, cmd


def get_routing_table() -> dict[str, dict]:
    """
    Return the full routing table showing shorthand -> CLI mappings.

    Used by /create-prompt to show what's available.
    """
    table: dict[str, dict] = {}
    cache_obj = load_cache_file()
    cache = cache_obj.to_dict() if cache_obj is not None else None

    for shorthand, req in sorted(_SHORTHAND.items(), key=lambda kv: kv[0]):
        desired_model = req.model_id
        if req.family == "local" and desired_model is None:
            desired_model = "local:*"
        try:
            cli, model_id, cmd = resolve_model(shorthand, preferred_cli=None)
            table[shorthand] = {
                "model_id": model_id,
                "cli": cli,
                "command": cmd,
                "status": "ready",
            }
        except ModelNotAvailable as exc:
            table[shorthand] = {
                "model_id": desired_model,
                "cli": None,
                "command": None,
                "status": "unavailable",
                "error": str(exc),
            }

    # Add raw installed model inventory (useful for UI/debug).
    if cache is not None:
        table["_inventory"] = {"models": get_available_models()}

    return table


def _render_markdown_table(headers: list[str], rows: list[list[str]]) -> str:
    safe_rows = [[(cell or "").replace("\n", " ") for cell in row] for row in rows]
    widths = [len(h) for h in headers]
    for row in safe_rows:
        for i, cell in enumerate(row):
            if i < len(widths):
                widths[i] = max(widths[i], len(cell))

    def fmt_row(cols: list[str]) -> str:
        padded = [cols[i].ljust(widths[i]) for i in range(len(headers))]
        return "| " + " | ".join(padded) + " |"

    sep = "| " + " | ".join("-" * w for w in widths) + " |"
    lines = [fmt_row(headers), sep]
    for row in safe_rows:
        row = (row + [""] * len(headers))[: len(headers)]
        lines.append(fmt_row(row))
    return "\n".join(lines)


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="daplug model router (uses /detect-clis cache)")
    p.add_argument("--resolve", metavar="SHORTHAND", help="Resolve a model shorthand")
    p.add_argument("--table", action="store_true", help="Print routing table")
    p.add_argument("--json", action="store_true", help="Emit JSON (for --resolve/--table)")
    return p


def main(argv: Optional[list[str]] = None) -> int:
    args = _build_parser().parse_args(argv)

    if args.resolve:
        try:
            cli, model_id, cmd = resolve_model(args.resolve, preferred_cli=None)
            payload = {"cli": cli, "model_id": model_id, "command": cmd}
            rc = 0
        except ModelNotAvailable as exc:
            payload = {"error": str(exc), "shorthand": args.resolve}
            rc = 2
        if args.json:
            print(json.dumps(payload, indent=2, sort_keys=True))
        else:
            print(json.dumps(payload, indent=2))
        return rc

    if args.table:
        table = get_routing_table()
        if args.json:
            print(json.dumps(table, indent=2, sort_keys=True))
            return 0

        rows: list[list[str]] = []
        for shorthand in sorted(k for k in table.keys() if not k.startswith("_")):
            entry = table[shorthand]
            status = "✅ Ready" if entry.get("status") == "ready" else "❌ Unavailable"
            rows.append(
                [
                    shorthand,
                    str(entry.get("model_id") or "-"),
                    str(entry.get("cli") or "-"),
                    status,
                ]
            )
        print(_render_markdown_table(["Shorthand", "Model", "CLI", "Status"], rows))
        return 0

    _build_parser().print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
