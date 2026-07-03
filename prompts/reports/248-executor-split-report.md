# Report: Split executor.py into focused modules (#248)

## Summary

The 3,508-line `skills/prompt-executor/scripts/executor.py` was split into six
focused sub-modules plus a thin entry point. Zero functional change. All 362
existing tests pass unchanged (modulo monkeypatch target moves). A new
`test_facade.py` pins the re-export surface (55 tests, 50+ names).

## Final Module Layout

| Module | Lines | Responsibility |
|--------|------:|----------------|
| `executor.py` | 710 | CLI entry point (`main()` + argparse), prompt resolution, facade re-exports |
| `paths.py` | 84 | `get_repo_root`, `_read_config_value`, `get_cli_logs_dir`, `get_worktree_dir`, `detect_default_branch` |
| `repostate.py` | 245 | Repo-state snapshot/delta, `_has_real_file_changes`, `_detect_stalled`, `_detect_impossible_gate` |
| `worktree.py` | 369 | `create_worktree`, `install_worktree_dependencies`, `normalize_worktree_path`, `ensure_worktree_permissions` |
| `models.py` | 605 | Model registry loading, CLI command building, `get_cli_info`, router resolution |
| `sandbox.py` | 437 | `BWRAP_PROFILES`, `resolve_sandbox_config`, `build_bwrap_args`, `sandbox_preflight`, `maybe_wrap_command_with_sandbox` |
| `loop.py` | 1282 | Loop state I/O, `check_completion_marker`, `wrap_prompt_with_verification_protocol`, `run_cli`, `run_verification_loop(_background)` |
| **Total** | **3732** | (3,508 original + 224 import headers/docstrings) |

`executor.py` went from 3,508 lines to 710 (79% reduction). The 710 lines
include ~140 lines of re-export imports and ~380 lines of `main()` / argparse.

## Dependency Graph (no cycles)

```
executor.py ──> paths.py
            ──> repostate.py
            ──> worktree.py ──> paths.py
            ──> models.py ──> paths.py
            ──> sandbox.py  (no cross-module deps)
            ──> loop.py ──> paths.py
                       ──> repostate.py
                       ──> sandbox.py
                       ──> models.py  (get_cli_info only)
```

- `paths.py`, `repostate.py`, `sandbox.py`: leaf modules, no cross-module imports.
- `worktree.py` imports from `paths.py`.
- `models.py` imports from `paths.py`.
- `loop.py` imports from `paths.py`, `repostate.py`, `sandbox.py`, `models.py`.
- `executor.py` imports from all six.

No circular imports exist.

## Code Adjustments (non-import)

Only one code line was changed beyond import adjustments:

**`loop.py` line 3047** (originally executor.py line 3047):
```python
# Before (in executor.py):
script_path = Path(__file__).resolve()

# After (in loop.py):
script_path = Path(__file__).resolve().parent / "executor.py"
```

**Reason:** `run_verification_loop_background` spawns `python3 <script> --loop-foreground`.
After the split, `__file__` points to `loop.py`, not `executor.py`. Appending
`.parent / "executor.py"` preserves the original behavior (spawns executor.py).
This is analogous to an import adjustment — a mechanical change to preserve
runtime behavior when code moves files.

All other code was moved verbatim. Only import headers and module docstrings
were added.

## Monkeypatch Target Moves

The test suite monkeypatches `executor.<name>` extensively. After the split,
code that calls a patched function resolves it through the **calling module's**
namespace, not executor's. When the caller moved to a new module, the patch
target had to move with it.

**Strategy:** For each patched function, the patch target was moved to the
module where the calling code lives. Where a function is called from both
executor.py (e.g. `main()`) and a sub-module, both modules are patched.

| Patched function | Moved from | Moved to | Reason | Test files affected |
|---|---|---|---|---|
| `get_loop_state_dir` | `executor` | `loop` (dual-patch) | `run_verification_loop` (loop.py) calls it through loop's namespace. `main()` calls it through executor's. | test_executor_logging, test_executor_variants, test_loop_verification, test_worktree_isolation |
| `run_cli_foreground` | `executor` | `loop` | `run_verification_loop` (loop.py) calls it through loop's namespace. No code in executor.py calls it directly. | test_executor_logging, test_loop_verification, test_worktree_isolation |
| `_resolve_router_command` | `executor` | `models` | `get_cli_info` (models.py) calls it through models' namespace. | test_executor_variants |
| `_require_claude_cli` | `executor` | `models` | `get_cli_info` (models.py) calls it through models' namespace. | test_executor_variants |
| `_read_config_value` | `executor` | `paths` | `get_worktree_dir` (paths.py) calls it through paths' namespace, which `create_worktree` uses. | test_worktree_isolation |
| `check_bwrap_available` | `executor` | `loop` | `run_cli` / `run_cli_foreground` (loop.py) call it through loop's namespace. | test_sandbox |
| `sandbox_preflight` | `executor` | `loop` | `run_cli` / `run_cli_foreground` (loop.py) call it through loop's namespace. | test_sandbox |
| `build_bwrap_args` | `executor` | `loop` | `run_cli` (loop.py) calls it through loop's namespace (imported from sandbox). | test_sandbox |

**Patches NOT moved (still target `executor`):**
- `executor.get_repo_root` — called by `main()` in executor.py; `get_cli_info` uses the passed `repo_root` parameter, not the function.
- `executor.get_cli_logs_dir` — called by `main()` in executor.py.
- `executor.run_cli` — called by `main()` in executor.py (re-exported from loop.py, resolved through executor's namespace).
- `executor.subprocess.Popen` / `executor.shutil.which` / `executor.Path.home` — these patch attributes on the **stdlib module objects themselves**, not on executor's namespace. Since all modules import the same `subprocess`/`shutil`/`pathlib.Path`, the patch is global and needs no change.

**No assertions changed.** Every test's assertions, expected values, and test
logic remain identical. Only the `monkeypatch.setattr` target object changed
from `executor` to `loop`/`models`/`paths` where the calling code moved.

## Verification Results

```
=== skills/prompt-executor/tests ===
105 passed
=== skills/cli-detector/tests ===
134 passed
=== skills/config-reader/tests ===
6 passed
=== skills/sprint/tests ===
12 passed
=== skills/at-prompt-runner/tests ===
50 passed
=== scripts/tests ===
55 passed
Total: 362 passed

=== test_executor_markers.py (scripts/) ===
18 passed

=== test_facade.py (new) ===
55 passed

=== manage-models.py check ===
Generated model documentation is in sync.

=== Entry point ===
executor.py --help         → require-diff found ✓
executor.py 009 --model codex → JSON output with repo/model ✓
executor.py --loop-status   → JSON loop states ✓

=== Facade ===
All 27 historically-patched names resolve on executor module ✓
```
