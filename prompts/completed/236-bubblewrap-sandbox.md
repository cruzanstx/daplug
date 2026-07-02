<objective>
Implement `--sandbox` bubblewrap support for `/run-prompt` so Linux users can run prompts with first-class sandbox isolation, eliminating the need for manual bwrap wrapper scripts.

This addresses GitHub issue #9: https://github.com/cruzanstx/daplug/issues/9
</objective>

<context>
daplug is a Claude Code plugin that runs prompts across multiple AI CLIs (codex, gemini, opencode, claude) with optional git worktree isolation and iterative verification loops.

The executor lives at `skills/prompt-executor/scripts/executor.py` and handles:
- Arg parsing (lines 2192-2255)
- Subprocess execution via `run_cli()` and `run_cli_foreground()` (lines 1674-1847)
- Existing isolation via `--worktree` flag and `get_sandbox_add_dirs()` helper

Linux users need a lightweight sandbox comparable to macOS seatbelt workflows, without forcing Docker/Podman. Bubblewrap provides this but policy setup is error-prone manually.

**Key files to modify:**
- `skills/prompt-executor/scripts/executor.py` — add sandbox flags and bwrap wrapper
- `skills/prompt-executor/SKILL.md` — document new flags
- `commands/run-prompt.md` — add CLI contract

**Reference implementations:**
- mini-swe-agent: `sandbox/bubblewrap.py` — Python bwrap integration
- Existing `get_sandbox_add_dirs()` function in executor.py (lines 1172-1216)
</context>

<requirements>
Implement the following MVP components in order:

## 1. CLI Arguments (executor.py argparse, lines ~2192-2255)

Add these flags alongside existing `--worktree`:

```
--sandbox          Enable sandboxing (Linux default: bubblewrap)
--sandbox-type     Backend override (bubblewrap)
--no-sandbox       Explicit opt-out
--sandbox-profile  Preset: strict|balanced|dev (default: balanced)
--sandbox-workspace  Override workspace path (default: repo root)
--sandbox-net      Network: on|off (default: by profile)
```

**Validation rules:**
- Error if both `--sandbox` and `--no-sandbox` are passed
- Error if `--sandbox-type` provided while sandboxing disabled
- On Linux, `--sandbox` without `--sandbox-type` defaults to `bubblewrap`
- On non-Linux, `--sandbox` with no type is a no-op (warn but proceed)

## 2. Sandbox Config Resolver (new function in executor.py)

```python
def resolve_sandbox_config(platform: str, args: argparse.Namespace, cwd: str) -> dict:
    """
    Resolve sandbox configuration from arguments and defaults.
    
    Returns:
        {
            "enabled": bool,
            "type": str | None,  # "bubblewrap" | None
            "profile": str,       # "strict" | "balanced" | "dev"
            "workspace": str,     # absolute path
            "network": bool,      # network enabled
        }
    """
```

Responsibilities:
- Default profile to `"balanced"`
- Default workspace to `cwd` (repo root)
- Network default by profile: `strict=False`, `balanced=True`, `dev=True`
- Validate platform compatibility

## 3. Bubblewrap Backend (new function in executor.py)

```python
def build_bwrap_args(config: dict, child_command: list[str]) -> list[str]:
    """
    Build bubblewrap argument list (NOT shell string).
    
    Returns the full command: ["bwrap", ...args, "--", ...child_command]
    """
```

**Argument construction:**
- `--unshare-all` — isolate all namespaces
- `--new-session` — new session for signal isolation
- `--die-with-parent` — cleanup on parent exit
- `--share-net` — iff `config["network"]` is True
- Readonly system binds: `/usr`, `/bin`, `/lib*`, `/etc/resolv.conf`, `/etc/hosts`, `/etc/ssl`
- Read-write binds:
  - `workspace` (repo root)
  - `~/.local/share/opencode` (opencode state)
  - `~/.cache/opencode` (opencode cache) — if `profile != "strict"`
  - `~/.config/opencode` (opencode config) — if `profile != "strict"`
  - Tool caches (`~/.cache/go-build`, `~/go/pkg/mod`, `~/.npm`) — if `profile == "dev"`
- tmpfs: `/tmp`, `/run`
- `--dev /dev` — device access

**IMPORTANT:** Use list construction, NEVER shell string concatenation.

## 4. Profile Presets (hardcoded dict, lines ~1200)

```python
BWRAP_PROFILES = {
    "strict": {
        "network": False,
        "writable": ["workspace", "opencode_state"],
        "minimal_env": True,
    },
    "balanced": {
        "network": True,
        "writable": ["workspace", "opencode_state", "opencode_cache", "opencode_config"],
        "minimal_env": True,
    },
    "dev": {
        "network": True,
        "writable": ["workspace", "opencode_state", "opencode_cache", "opencode_config", "tool_caches"],
        "minimal_env": False,
    },
}
```

## 5. Error Handling UX

**If `bwrap` missing:**
```
Error: bubblewrap (bwrap) not found in PATH.

Install with:
  apt:   sudo apt install bubblewrap
  dnf:   sudo dnf install bubblewrap
  pacman: sudo pacman -S bubblewrap

To run without sandbox: add --no-sandbox
```

**If launch fails:**
- Print generated config summary: `type=bubblewrap, profile=balanced, workspace=/path, network=on`
- Return non-zero with remediation hints

## 6. Integration with run_cli() and run_cli_foreground()

Modify these functions to:
1. Check if sandbox config is enabled
2. If enabled and type is `"bubblewrap"`: wrap child command with `build_bwrap_args()`
3. Spawn the wrapped command instead of raw child

The sandbox wrapper should be transparent to the rest of the execution flow (same exit code handling, same logging).
</requirements>

<implementation>
**Phase 1: Add argparse flags** (lines 2192-2255)
- Add `--sandbox`, `--sandbox-type`, `--no-sandbox`, `--sandbox-profile`, `--sandbox-workspace`, `--sandbox-net`
- Add validation in main() after parse_args()

**Phase 2: Create resolver and profile dict** (lines ~1150-1220, near get_sandbox_add_dirs)
- Add `BWRAP_PROFILES` constant
- Add `resolve_sandbox_config()` function

**Phase 3: Create bwrap argument builder** (lines ~1220-1350)
- Add `build_bwrap_args()` function
- Add `check_bwrap_available()` helper

**Phase 4: Integrate with subprocess execution** (lines 1674-1847)
- Modify `run_cli()` to accept sandbox config
- Modify `run_cli_foreground()` to accept sandbox config
- Wrap command with bwrap when sandbox enabled

**Phase 5: Update documentation**
- `skills/prompt-executor/SKILL.md` — add flag documentation
- `commands/run-prompt.md` — add to arguments table

**Phase 6: Tests** (new file: `skills/prompt-executor/tests/test_sandbox.py`)
- Unit tests for resolver validation
- Unit tests for bwrap arg builder per profile
- Integration test for command wrapping

**Constraints:**
- NEVER use shell string concatenation for bwrap args
- NEVER silently proceed if bwrap is missing (fail with actionable error)
- MUST preserve existing behavior when sandbox is not enabled
- MUST propagate exact child exit code through bwrap
</implementation>

<output>
Create/modify files:
- `skills/prompt-executor/scripts/executor.py` — add sandbox subsystem
- `skills/prompt-executor/SKILL.md` — document new flags
- `commands/run-prompt.md` — add to arguments table
- `skills/prompt-executor/tests/test_sandbox.py` — unit tests (new file)
</output>

<verification>
**Unit Tests** (REQUIRED):
```bash
cd skills/prompt-executor && python3 -m pytest tests/test_sandbox.py -v
```

Test coverage:
- [ ] `resolve_sandbox_config()` defaults
- [ ] `resolve_sandbox_config()` validation errors (conflicting flags)
- [ ] `build_bwrap_args()` output for each profile (strict/balanced/dev)
- [ ] `build_bwrap_args()` network flag toggle
- [ ] `check_bwrap_available()` detection

**Integration Tests** (Linux CI only):
```bash
# Verify bwrap wraps child command
python3 scripts/executor.py 001 --model codex --sandbox --info-only
# Should show bwrap in command preview

# Verify missing bwrap error
PATH="" python3 scripts/executor.py 001 --model codex --sandbox --run
# Should exit non-zero with install hint
```

**Manual Verification:**
1. Run a prompt with `--sandbox` on Linux — verify bwrap is invoked
2. Run same prompt with `--no-sandbox` — verify direct execution
3. Run with `--sandbox-profile strict` — verify network is blocked
4. Remove bwrap from PATH, run with `--sandbox` — verify helpful error message
</verification>

<success_criteria>
- [ ] Linux user can run `/run-prompt <id> --sandbox` without manual script authoring
- [ ] `--sandbox` defaults to bubblewrap on Linux
- [ ] `--no-sandbox` explicitly disables sandboxing
- [ ] `--sandbox-profile strict|balanced|dev` controls isolation level
- [ ] Missing bwrap produces actionable error with install hints
- [ ] All unit tests pass
- [ ] Documentation updated in SKILL.md and run-prompt.md
- [ ] No breaking changes to existing `--worktree` behavior
</success_criteria>