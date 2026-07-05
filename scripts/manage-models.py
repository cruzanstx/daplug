#!/usr/bin/env python3
"""
Model Management Utility for daplug.

scripts/models.json is the single source of truth. This tool lists registry
entries, regenerates markdown snippets, verifies generated snippets for CI, and
interactively adds registry entries.
"""

from __future__ import annotations

import argparse
import difflib
import json
import re
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Callable

BEGIN = "<!-- BEGIN GENERATED: {name} -->"
END = "<!-- END GENERATED: {name} -->"
SUPPORTED_VARIANTS = {"high", "xhigh"}
ALLOWED_STDIN_MODES = {None, "dash", "arg", "stdin"}
REQUIRED_MODEL_FIELDS = {
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
REQUIRED_DOC_FIELDS = {
    "family",
    "cli_label",
    "actual_model",
    "option_description",
    "reference_cli",
    "reference_description",
    "readme_section",
    "readme_model",
    "best_for",
    "prompt_description",
    "menu_note",
    "include_in_prompt_guides",
}


class RegistryError(RuntimeError):
    """Raised when scripts/models.json is malformed."""


class GenerationError(RuntimeError):
    """Raised when a generated region cannot be inserted."""


def get_repo_root() -> Path:
    """Get the repository root directory."""
    return Path(__file__).resolve().parent.parent


def registry_path(repo_root: Path) -> Path:
    return repo_root / "scripts" / "models.json"


def load_registry(repo_root: Path) -> dict:
    path = registry_path(repo_root)
    if not path.exists():
        raise RegistryError(f"Model registry not found: {path}")
    try:
        data = json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        raise RegistryError(f"Model registry is invalid JSON: {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise RegistryError("Model registry must be a JSON object")
    if data.get("schema_version") != 1:
        raise RegistryError("Model registry schema_version must be 1")
    models = data.get("models")
    if not isinstance(models, list) or not models:
        raise RegistryError("Model registry must contain a non-empty models list")

    seen: set[str] = set()
    for index, model in enumerate(models):
        if not isinstance(model, dict):
            raise RegistryError(f"Model entry #{index + 1} must be an object")
        missing = sorted(REQUIRED_MODEL_FIELDS - set(model))
        name = model.get("name", f"#{index + 1}")
        if missing:
            raise RegistryError(f"Model entry {name} missing fields: {', '.join(missing)}")
        if not isinstance(name, str) or not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", name):
            raise RegistryError(f"Model entry #{index + 1} has invalid name: {name!r}")
        if name in seen:
            raise RegistryError(f"Duplicate model entry: {name}")
        seen.add(name)
        if model["default_variant"] is not None and model["default_variant"] not in SUPPORTED_VARIANTS:
            raise RegistryError(f"Model entry {name} has invalid default_variant")
        if not isinstance(model["env"], dict) or not all(isinstance(key, str) and isinstance(value, str) for key, value in model["env"].items()):
            raise RegistryError(f"Model entry {name} env must be a string map")
        if model["stdin_mode"] not in ALLOWED_STDIN_MODES:
            raise RegistryError(f"Model entry {name} has invalid stdin_mode")
        if not isinstance(model["command"], list) or not all(isinstance(item, str) for item in model["command"]):
            raise RegistryError(f"Model entry {name} command must be a list of strings")
        routing = model["routing"]
        if not isinstance(routing, dict) or not isinstance(routing.get("cli_overrides"), list):
            raise RegistryError(f"Model entry {name} has invalid routing metadata")
        docs = model["docs"]
        if not isinstance(docs, dict):
            raise RegistryError(f"Model entry {name} docs must be an object")
        doc_missing = sorted(REQUIRED_DOC_FIELDS - set(docs))
        if doc_missing:
            raise RegistryError(f"Model entry {name} docs missing fields: {', '.join(doc_missing)}")

    for model in models:
        alias_of = model.get("alias_of")
        if alias_of is not None and alias_of not in seen:
            raise RegistryError(f"Model entry {model['name']} aliases unknown model: {alias_of}")

    return data


def models(registry: dict) -> list[dict]:
    return list(registry["models"])


def model_names(registry: dict) -> list[str]:
    return [model["name"] for model in models(registry)]


def docs(model: dict, key: str) -> str:
    return str(model["docs"][key])


def strip_provider(model_id: str) -> str:
    return model_id.split(":", 1)[1] if ":" in model_id else model_id


def opencode_model_spec(model_id: str) -> str:
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


def command_env(default_cli: str, command: list[str]) -> dict[str, str]:
    if default_cli == "codex" and "--profile" in command:
        try:
            profile = command[command.index("--profile") + 1]
        except (ValueError, IndexError):
            return {}
        if str(profile).startswith("local"):
            return {"LMSTUDIO_API_KEY": "lm-studio"}
    return {}


def stdin_mode_for_cli(default_cli: str) -> str | None:
    if default_cli == "subagent":
        return None
    if default_cli == "codex":
        return "dash"
    if default_cli == "claude":
        return "stdin"
    return "arg"


def default_command(
    default_cli: str,
    model_id: str,
    codex_profile: str | None,
    claude_model_flag: str | None,
    default_variant: str | None,
) -> list[str]:
    if default_cli == "subagent":
        if default_variant:
            raise RegistryError("Subagent models cannot have a default variant")
        return []
    if default_cli == "codex":
        command = ["codex", "exec", "--full-auto"]
        if codex_profile:
            command.extend(["--profile", codex_profile])
        else:
            stripped = strip_provider(model_id)
            if stripped and stripped != "gpt-5.5":
                command.extend(["-m", stripped])
        if default_variant:
            command.extend(["-c", f'model_reasoning_effort="{default_variant}"'])
        return command
    if default_cli == "opencode":
        command = ["opencode", "run", "--format", "json", "-m", opencode_model_spec(model_id)]
        if model_id.startswith("lmstudio:"):
            # Local models use the lean built-in agent without plugins: the plugin
            # default agent (Sisyphus) plus oh-my-openagent tool schemas cost ~63k
            # input tokens per turn, which local context windows can't afford.
            command.extend(["--pure", "--agent", "build"])
        if default_variant:
            command.extend(["--variant", default_variant])
        return command
    if default_cli == "gemini":
        if default_variant:
            raise RegistryError("Gemini models cannot have a default variant")
        return ["gemini", "-y", "-m", strip_provider(model_id), "-p"]
    if default_cli == "claude":
        if default_variant:
            raise RegistryError("Claude CLI models cannot have a default variant")
        command = [
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
        if claude_model_flag:
            command.extend(["--model", claude_model_flag])
        return command
    raise RegistryError(f"Unsupported default CLI for command generation: {default_cli}")


def group_models(registry: dict, doc_key: str) -> dict[str, list[dict]]:
    grouped: dict[str, list[dict]] = {}
    for model in models(registry):
        grouped.setdefault(docs(model, doc_key), []).append(model)
    return grouped


def marker(name: str, content: str) -> str:
    body = content.strip("\n")
    return f"{BEGIN.format(name=name)}\n{body}\n{END.format(name=name)}"


def replace_marked_region(text: str, name: str, generated: str) -> tuple[str, bool]:
    begin = BEGIN.format(name=name)
    end = END.format(name=name)
    pattern = re.compile(re.escape(begin) + r".*?" + re.escape(end), re.S)
    replacement = marker(name, generated)
    new_text, count = pattern.subn(replacement, text, count=1)
    return new_text, bool(count)


def replace_region(text: str, name: str, generated: str, fallback: str) -> str:
    marked, replaced = replace_marked_region(text, name, generated)
    if replaced:
        return marked
    replacement = marker(name, generated)
    new_text, count = re.subn(fallback, replacement, text, count=1, flags=re.S | re.M)
    if count != 1:
        raise GenerationError(f"Could not locate insertion point for generated region {name}")
    return new_text



def replace_region_after(text: str, name: str, generated: str, anchor: str, fallback: str) -> str:
    marked, replaced = replace_marked_region(text, name, generated)
    if replaced:
        return marked
    index = text.find(anchor)
    if index == -1:
        raise GenerationError(f"Could not locate anchor for generated region {name}: {anchor}")
    head = text[:index]
    tail = text[index:]
    replacement = marker(name, generated)
    new_tail, count = re.subn(fallback, replacement, tail, count=1, flags=re.S | re.M)
    if count != 1:
        raise GenerationError(f"Could not locate insertion point for generated region {name}")
    return head + new_tail

def comma_list(names: list[str]) -> str:
    return ", ".join(names)


def render_skill_model_options(registry: dict) -> str:
    names = comma_list(model_names(registry))
    highlights = [
        "  - `glm52`: GLM-5.2 via Z.AI / OpenCode (1M context)",
        "  - `synthetic`: GLM-5.2 via Synthetic / OpenCode (`syn:large:text`, requires `SYNTHETIC_API_KEY`)",
    ]
    return "\n".join([f"- `--model, -m`: {names}", *highlights])


def render_run_prompt_model_argument(registry: dict) -> str:
    names = comma_list(model_names(registry))
    return (
        f"| `--model, -m` | {names} "
        "(codex/codex-high/codex-xhigh default to GPT-5.5; `gpt55*` are explicit GPT-5.5 shorthands) |"
    )


def render_preferred_agent_options(registry: dict) -> str:
    lines = [f"- `{model['name']}` - {docs(model, 'option_description')}" for model in models(registry)]
    lines.insert(25, "- Google shorthands prefer Antigravity CLI (`agy`) when healthy and fall back to legacy `gemini`.")
    return "\n".join(lines)


def render_skill_reference_table(registry: dict) -> str:
    lines = ["| Model | CLI | Description |", "|-------|-----|-------------|"]
    for model in models(registry):
        lines.append(f"| {model['name']} | {docs(model, 'reference_cli')} | {docs(model, 'reference_description')} |")
    return "\n".join(lines)


def render_claude_shorthand_table(registry: dict) -> str:
    lines = ["| Shorthand | CLI | Actual Model |", "|-----------|-----|--------------|"]
    for model in models(registry):
        lines.append(f"| `{model['name']}` | {docs(model, 'cli_label')} | {docs(model, 'actual_model')} |")
    return "\n".join(lines)


def render_available_models(registry: dict) -> str:
    lines = ["All available models for /daplug:run-prompt --model:", ""]
    headings = {
        "Claude": "**Claude Family:** (check: `claude.five_hour.used`, `claude.seven_day.used`)",
        "OpenAI Codex": "**OpenAI Codex Family:** (check: `codex.primary_window.used`, `codex.secondary_window.used`)",
        "Google Gemini": "**Google Gemini Family:** (check: `gemini.models.<model>.used` for each; `agy` is preferred when healthy, legacy `gemini` is fallback)",
        "Z.AI / OpenCode": "**Z.AI / OpenCode Models:** (check: `zai.token_quota.percentage` where applicable)",
        "Synthetic": "**Synthetic Models:** (check request quota from `/v2/quotas`; requires `SYNTHETIC_API_KEY`)",
        "Local": "**Local Models:** (opencode + LMStudio; no hosted quota)",
    }
    for family, family_models in group_models(registry, "family").items():
        lines.append(headings.get(family, f"**{family}:**"))
        for model in family_models:
            lines.append(f"- `{model['name']}` - {docs(model, 'prompt_description')}")
        lines.append("")
    lines.extend([
        "**Gemini Model Mapping:**",
        "Antigravity (`agy`) maps legacy shorthands to the closest current `agy models` display names; legacy `gemini` keeps these API model IDs.",
        "| Shorthand | API Model | Quota Bucket |",
        "|-----------|-----------|--------------|",
    ])
    for model in [m for m in models(registry) if m["routing"].get("google")]:
        api_model = strip_provider(model["model_id"])
        lines.append(f"| `{model['name']}` | {api_model} | {api_model} |")
    return "\n".join(lines).rstrip()


def render_create_prompt_recommendations(registry: dict) -> str:
    recommendations = registry.get("docs", {}).get("create_prompt_recommendations", [])
    lines = ["| Condition | Recommended Model | Reason |", "|-----------|-------------------|--------|"]
    for item in recommendations:
        lines.append(f"| `{item['condition']}` | `{item['model']}` | {item['reason']} |")
    return "\n".join(lines)


def render_llms_recommendations(registry: dict) -> str:
    recommendations = registry.get("docs", {}).get("llms_txt_recommendations", [])
    lines = ["| Priority | Model | Reason |", "|----------|-------|--------|"]
    for index, item in enumerate(recommendations, 1):
        lines.append(f"| {index} | {item['model']} | {item['reason']} |")
    return "\n".join(lines)


def render_model_selection_menu(registry: dict, choose_label: str) -> str:
    lines = []
    option = 1
    sections = [
        ("Claude", "Claude"),
        ("Codex (OpenAI)", "OpenAI Codex"),
        ("Gemini (Google)", "Google Gemini"),
        ("Z.AI / OpenCode", "Z.AI / OpenCode"),
        ("Synthetic", "Synthetic"),
        ("Local", "Local"),
    ]
    grouped = group_models(registry, "family")
    for title, family in sections:
        family_models = grouped.get(family, [])
        if not family_models:
            continue
        status = "{show each model's usage}" if family == "Google Gemini" else "{usage status}"
        lines.append(f"  **{title}:** {status}")
        for model in family_models:
            usage = "{X}% used - "
            if family in {"Synthetic"}:
                usage = "{requests}/{limit} requests - "
            elif family == "Local":
                usage = ""
            elif family == "Claude":
                usage = ""
            lines.append(f"  {option}. {model['name']} - {usage}{docs(model, 'menu_note')}")
            option += 1
        lines.append("")
    total = option - 1
    lines.append(f"  {choose_label} (1-{total}), or type model with flags (e.g., 'codex --worktree --loop'): _")
    return "\n".join(lines).rstrip()


def render_readme_model_tiers(registry: dict) -> str:
    lines = [
        "### Model Tiers",
        "",
        "These tables are generated from `scripts/models.json`.",
        "",
    ]
    for section, section_models in group_models(registry, "readme_section").items():
        lines.append(f"#### {section}")
        lines.append("")
        if section == "Synthetic":
            lines.append("Synthetic shorthands route through OpenCode's `synthetic` provider and require `SYNTHETIC_API_KEY`.")
            lines.append("")
        lines.append("| Shorthand | Model | Best For |")
        lines.append("|-----------|-------|----------|")
        for model in section_models:
            lines.append(f"| `{model['name']}` | {docs(model, 'readme_model')} | {docs(model, 'best_for')} |")
        lines.append("")
    lines.extend([
        "**When to use GPT-5.2 vs GPT-5.5:**",
        "- **GPT-5.5**: Best when plans are clear, need fast execution (combines codex + reasoning)",
        "- **GPT-5.2**: Best for ambiguous problems, research, methodical analysis",
    ])
    return "\n".join(lines).rstrip()


def render_claude_model_notes() -> str:
    return "\n".join([
        "Google shorthands prefer Antigravity CLI (`agy`) when it is installed and healthy. The legacy `gemini` CLI remains supported as fallback and for explicit `--cli gemini` runs.",
        "",
        "**GLM-5.2 long-context note:** Z.AI Coding Plan uses endpoint `https://api.z.ai/api/coding/paas/v4` with raw model ID `glm-5.2` and a 1M context window. OpenCode model refs use `zai/glm-5.2`; Claude Code env vars use `glm-5.2[1m]` for `ANTHROPIC_DEFAULT_SONNET_MODEL` and `ANTHROPIC_DEFAULT_OPUS_MODEL`, plus `CLAUDE_CODE_AUTO_COMPACT_WINDOW=1000000`. daplug does not set context-window flags for OpenCode; the Coding Plan endpoint activates the 1M window.",
        "",
        '**Synthetic note:** Synthetic shorthands use OpenCode provider refs such as `synthetic/syn:large:text` and require `SYNTHETIC_API_KEY`. OpenAI-compatible base URL: `https://api.synthetic.new/openai/v1`; Anthropic-compatible base URL: `https://api.synthetic.new/anthropic`; quota endpoint: `GET https://api.synthetic.new/v2/quotas` returns `subscription.requests`, `subscription.limit`, and `subscription.renewsAt` without counting against quota. Minimal `opencode.json` provider example: `{"provider":{"synthetic":{"npm":"@ai-sdk/openai-compatible","options":{"baseURL":"https://api.synthetic.new/openai/v1","apiKey":"{env:SYNTHETIC_API_KEY}"},"models":{"syn:large:text":{"name":"Synthetic GLM-5.2"}}}}}`.',
        "",
        "**OpenCode (opencode) note:** daplug runs OpenCode with `--format json` for clean, parseable logs (no PTY). To avoid interactive permission prompts in headless runs, configure `~/.config/opencode/opencode.json`.",
    ])


def render_generated_locations() -> str:
    rows = [
        (1, "`scripts/models.json`", "Runtime model registry source of truth"),
        (2, "`skills/prompt-executor/scripts/executor.py`", "Runtime maps and `--model` argparse choices derived from registry"),
        (3, "`skills/prompt-executor/SKILL.md`", "`--model` options list"),
        (4, "`skills/prompt-executor/SKILL.md`", "Model Reference table"),
        (5, "`commands/run-prompt.md`", "`--model` argument description"),
        (6, "`commands/prompts.md`", "preferred_agent options list"),
        (7, "`commands/create-prompt.md`", "`<available_models>` section"),
        (8, "`commands/create-prompt.md`", "Recommendation logic table"),
        (9, "`commands/create-prompt.md`", "Model selection menus (3 generated regions)"),
        (10, "`commands/create-llms-txt.md`", "`<available_models>` section"),
        (11, "`commands/create-llms-txt.md`", "Recommendation logic table"),
        (12, "`commands/create-llms-txt.md`", "Model selection menu"),
        (13, "`README.md`", "Model Tiers section"),
        (14, "`CLAUDE.md`", "Model Shorthand Reference table and generated-location map"),
    ]
    lines = ["| # | File | Generated Region |", "|---|------|------------------|"]
    for number, path, section in rows:
        lines.append(f"| {number} | {path} | {section} |")
    return "\n".join(lines)


def render_managing_models_section() -> str:
    return "\n".join([
        "## Managing Models",
        "",
        "Model definitions live in `scripts/models.json`. Adding, removing, or modifying a model should require editing that file, then regenerating derived documentation.",
        "",
        "### Using the Management Script",
        "",
        "```bash",
        "# List all current models",
        "python3 scripts/manage-models.py list",
        "",
        "# Regenerate markdown sections from scripts/models.json",
        "python3 scripts/manage-models.py generate",
        "",
        "# CI verifier: exits non-zero if generate would change files",
        "python3 scripts/manage-models.py check",
        "",
        "# Add a new model interactively, then regenerate docs",
        "python3 scripts/manage-models.py add",
        "```",
        "",
        "### Generated Locations",
        "",
        marker("generated-model-locations", render_generated_locations()),
        "",
        "Generated regions are bounded by HTML comments like `<!-- BEGIN GENERATED: model-shorthand-table -->` and `<!-- END GENERATED: model-shorthand-table -->`. Hand-written prose around those markers is preserved.",
        "",
        "### Verification",
        "",
        "After adding a model, verify it works:",
        "",
        "```bash",
        "# Check model appears in help",
        "python3 skills/prompt-executor/scripts/executor.py --help | grep model-name",
        "",
        "# Test command generation",
        "python3 skills/prompt-executor/scripts/executor.py 009 --model model-name",
        "```",
    ])


Target = tuple[str, Callable[[dict], str], str]


def update_skill(path: Path, registry: dict) -> str:
    text = path.read_text()
    text = replace_region(text, "skill-model-options", render_skill_model_options(registry), r"- `--model, -m`:.*?(?=\n- `--cli`)")
    text = replace_region(text, "skill-model-reference", render_skill_reference_table(registry), r"\| Model \| CLI \| Description \|\n\|[-| ]+\|\n.*?(?=\n\nOpenCode runs include)")
    return text


def update_run_prompt(path: Path, registry: dict) -> str:
    text = path.read_text()
    text = re.sub(r"argument-hint: <prompt\(s\)> \[--model .*?\] \[--cli", "argument-hint: <prompt(s)> [--model <model>] [--moa <m1,m2,...>] [--cli", text, count=1)
    text = replace_region(text, "run-prompt-model-argument", render_run_prompt_model_argument(registry), r"\| `--model, -m` \| .*? \|")
    return text


def update_prompts(path: Path, registry: dict) -> str:
    text = path.read_text()
    text = replace_region(text, "preferred-agent-options", render_preferred_agent_options(registry), r"- `claude` - Claude Code.*?(?=\n\n3\. \*\*After user selects)")
    return text


def update_create_prompt(path: Path, registry: dict) -> str:
    text = path.read_text()
    text = replace_region(text, "create-prompt-available-models", render_available_models(registry), r"(?<=<available_models>\n).*?(?=\n</available_models>)")
    text = replace_region(text, "create-prompt-recommendations", render_create_prompt_recommendations(registry), r"\| Task Type.*?\| Default.*?\|\s*(?=\n\n\*\*Step 3)" )
    menu_pattern = r"  \*\*Claude:\*\* \{usage status\}.*?Choose \(1-29\), or type model with flags \(e\.g\., 'codex --loop'\): _"
    text = replace_region_after(text, "create-prompt-selection-menu", render_model_selection_menu(registry, "Choose"), "<single_prompt_scenario>", menu_pattern)
    text = replace_region_after(text, "create-prompt-parallel-selection-menu", render_model_selection_menu(registry, "Choose"), "<parallel_scenario>", menu_pattern)
    text = replace_region_after(text, "create-prompt-sequential-selection-menu", render_model_selection_menu(registry, "Choose"), "<sequential_scenario>", menu_pattern)
    return text


def update_create_llms(path: Path, registry: dict) -> str:
    text = path.read_text()
    text = replace_region(text, "create-llms-available-models", render_available_models(registry), r"(?<=<available_models>\n).*?(?=\n</available_models>)")
    text = replace_region(text, "create-llms-recommendations", render_llms_recommendations(registry), r"\| Priority \| Model \| Reason \|.*?(?=\n\n\*\*Recommended flags)")
    text = replace_region(text, "create-llms-selection-menu", render_model_selection_menu(registry, "Choose"), r"  \*\*Claude:\*\* \{usage status\}.*?Choose \(1-28\), or type model with flags \(e\.g\., 'gpt52-xhigh --worktree --loop'\): _")
    return text


def update_readme(path: Path, registry: dict) -> str:
    text = path.read_text()
    text = replace_region(text, "readme-model-tiers", render_readme_model_tiers(registry), r"### Google Gemini Runner Model Tiers.*?(?=\n## Worktree Auto-Install)")
    return text


def update_claude(path: Path, registry: dict) -> str:
    text = path.read_text()
    shorthand = render_claude_shorthand_table(registry) + "\n\n" + render_claude_model_notes()
    text = replace_region(text, "model-shorthand-table", shorthand, r"\| Shorthand \| CLI \| Actual Model \|.*?(?=\n## Managing Models)")
    text = re.sub(r"## Managing Models.*?(?=\n## Releasing)", render_managing_models_section() + "\n", text, count=1, flags=re.S)
    return text


TARGETS: list[tuple[str, Callable[[Path, dict], str]]] = [
    ("skills/prompt-executor/SKILL.md", update_skill),
    ("commands/run-prompt.md", update_run_prompt),
    ("commands/prompts.md", update_prompts),
    ("commands/create-prompt.md", update_create_prompt),
    ("commands/create-llms-txt.md", update_create_llms),
    ("README.md", update_readme),
    ("CLAUDE.md", update_claude),
]


def render_all(repo_root: Path) -> dict[Path, str]:
    registry = load_registry(repo_root)
    rendered: dict[Path, str] = {}
    for relative, updater in TARGETS:
        path = repo_root / relative
        if not path.exists():
            raise GenerationError(f"Target file not found: {relative}")
        rendered[path] = updater(path, registry)
    return rendered


def generate_models(repo_root: Path, write: bool = True) -> list[Path]:
    rendered = render_all(repo_root)
    changed: list[Path] = []
    for path, new_text in rendered.items():
        if path.read_text() != new_text:
            changed.append(path)
            if write:
                path.write_text(new_text)
    return changed


def check_models(repo_root: Path) -> bool:
    changed = generate_models(repo_root, write=False)
    if not changed:
        print("Generated model documentation is in sync.")
        return True

    print("Generated model documentation is out of sync. Run: python3 scripts/manage-models.py generate", file=sys.stderr)
    for path in changed:
        old = path.read_text().splitlines(keepends=True)
        new = render_all(repo_root)[path].splitlines(keepends=True)
        relative = path.relative_to(repo_root)
        print(f"\n--- {relative}", file=sys.stderr)
        print(f"+++ {relative} (generated)", file=sys.stderr)
        for line in difflib.unified_diff(old, new, fromfile=str(relative), tofile=f"{relative} (generated)"):
            print(line, end="", file=sys.stderr)
    return False


def list_models(repo_root: Path) -> None:
    registry = load_registry(repo_root)
    items = models(registry)
    print(f"Found {len(items)} models in scripts/models.json:\n")
    print(f"{'Model':<15} {'Display':<58} {'CLI':<10}")
    print("-" * 88)
    for model in items:
        display = str(model["display"])
        if len(display) > 55:
            display = display[:52] + "..."
        print(f"{model['name']:<15} {display:<58} {model['default_cli']:<10}")


def prompt_bool(prompt: str, default: bool = False) -> bool:
    suffix = "Y/n" if default else "y/N"
    value = input(f"{prompt} [{suffix}]: ").strip().lower()
    if not value:
        return default
    return value in {"y", "yes"}


def add_model_interactive(repo_root: Path) -> None:
    registry = load_registry(repo_root)
    existing = set(model_names(registry))

    print("Add New Model\n")
    name = input("Model shorthand name (e.g., 'gpt56', 'gemini-fast'): ").strip()
    if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", name):
        raise RegistryError("Model name must be lowercase words separated by hyphens")
    if name in existing:
        raise RegistryError(f"Model '{name}' already exists")

    model_id = input("Model ID with provider prefix (e.g., openai:gpt-5.6): ").strip()
    default_cli = input("Default CLI (codex/opencode/gemini/claude/subagent) [codex]: ").strip() or "codex"
    supports_reasoning = prompt_bool("Supports Codex high/xhigh reasoning", default=default_cli == "codex")
    codex_profile = input("Codex profile (blank for none): ").strip() or None
    claude_model_flag = input("Claude --model flag (blank for none): ").strip() or None
    alias_of = input("Alias of existing shorthand (blank for none): ").strip() or None
    default_variant = input("Default variant high/xhigh (blank for none): ").strip() or None
    display = input(f"Display [{name} ({model_id})]: ").strip() or f"{name} ({model_id})"
    family = input("Docs family [OpenAI Codex]: ").strip() or "OpenAI Codex"
    description = input("Docs description: ").strip() or display
    readme_section = input(f"README section [{family}]: ").strip() or family
    best_for = input("README Best For: ").strip() or description
    force_direct = prompt_bool("Force direct OpenCode routing", default=default_cli == "opencode")
    google = prompt_bool("Google shorthand", default=model_id.startswith("google:"))
    synthetic = prompt_bool("Synthetic shorthand", default=model_id.startswith("synthetic:"))
    overrides_raw = input("Supported --cli overrides, comma-separated (blank for default CLI only): ").strip()
    cli_overrides = [item.strip() for item in overrides_raw.split(",") if item.strip()] or [default_cli]
    command = default_command(default_cli, model_id, codex_profile, claude_model_flag, default_variant)

    entry = {
        "name": name,
        "display": display,
        "model_id": model_id,
        "default_cli": default_cli,
        "supports_codex_reasoning": supports_reasoning,
        "codex_profile": codex_profile,
        "claude_model_flag": claude_model_flag,
        "alias_of": alias_of,
        "default_variant": default_variant,
        "env": command_env(default_cli, command),
        "stdin_mode": stdin_mode_for_cli(default_cli),
        "command": command,
        "routing": {
            "cli_overrides": cli_overrides,
            "force_direct_opencode": force_direct,
            "google": google,
            "synthetic": synthetic,
        },
        "docs": {
            "family": family,
            "cli_label": "agy/gemini" if google else default_cli,
            "actual_model": strip_provider(model_id),
            "option_description": description,
            "reference_cli": default_cli,
            "reference_description": best_for,
            "readme_section": readme_section,
            "readme_model": strip_provider(model_id),
            "best_for": best_for,
            "prompt_description": description,
            "menu_note": best_for,
            "include_in_prompt_guides": True,
        },
    }

    registry["models"].append(entry)
    registry_path(repo_root).write_text(json.dumps(registry, indent=2, ensure_ascii=True) + "\n")
    changed = generate_models(repo_root, write=True)
    print(f"Added {name} to scripts/models.json and regenerated {len(changed)} files.")


def copy_repo_for_check(repo_root: Path, tmp_root: Path) -> None:
    for relative, _updater in TARGETS:
        source = repo_root / relative
        dest = tmp_root / relative
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, dest)
    scripts_dir = tmp_root / "scripts"
    scripts_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(registry_path(repo_root), scripts_dir / "models.json")


def main() -> int:
    parser = argparse.ArgumentParser(description="Manage daplug model registry and generated docs")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("list", help="List all models in scripts/models.json")
    subparsers.add_parser("generate", help="Regenerate markdown sections from scripts/models.json")
    subparsers.add_parser("check", help="Fail if generated markdown sections are out of sync")
    subparsers.add_parser("add", help="Interactively add a model to scripts/models.json, then generate")
    args = parser.parse_args()

    repo_root = get_repo_root()
    try:
        if args.command == "list":
            list_models(repo_root)
            return 0
        if args.command == "generate":
            changed = generate_models(repo_root, write=True)
            if changed:
                print("Regenerated model documentation:")
                for path in changed:
                    print(f"  - {path.relative_to(repo_root)}")
            else:
                print("Generated model documentation already in sync.")
            return 0
        if args.command == "check":
            with tempfile.TemporaryDirectory(prefix="daplug-model-check-") as tmp:
                tmp_root = Path(tmp)
                copy_repo_for_check(repo_root, tmp_root)
                ok = check_models(tmp_root)
            return 0 if ok else 1
        if args.command == "add":
            add_model_interactive(repo_root)
            return 0
    except (RegistryError, GenerationError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
