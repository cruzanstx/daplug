<objective>
Fix daplug's Antigravity CLI (`agy`) headless execution so long-running prompts no longer die on agy's default `--print` timeout, and so daplug can observe progress, distinguish failure modes, and detect stalls. This is the code path behind every Google shorthand (`gemini`, `gemini37*`, `agy`, etc.) when `--worktree --sandbox --loop` runs take longer than agy's built-in print timeout. Today the run is killed by agy, the log ends abruptly, and the verification loop cannot tell "AGY timed out" from "AGY finished with an error".

Do NOT bump the plugin version, commit, push, tag, or create a release. Leave the working tree with the implementation and tests only.
</objective>

<context>
daplug is a Claude Code plugin (Python 3 scripts, no framework). Read `./CLAUDE.md` first for conventions, the model registry workflow, and the release rules you must NOT trigger.

Files that own the AGY path today (read all of them before editing):
- `./skills/prompt-executor/scripts/models.py` — `_build_agy_command()` (~line 393) returns `["agy", "--model", <display>, "--dangerously-skip-permissions", "--print"]`; `get_cli_info()` sets `stdin_mode="arg"` for agy.
- `./skills/cli-detector/scripts/router.py` — duplicate agy argv builder (~line 609) used by preferred-agent routing.
- `./scripts/manage-models.py` (~line 230) and `./scripts/models.json` (`command` arrays and `reference_cli` strings for agy entries) — registry source of truth; `python3 scripts/manage-models.py generate` regenerates the documented argv in `CLAUDE.md`, `README.md`, `skills/prompt-executor/SKILL.md`, and `commands/*.md`; `python3 scripts/manage-models.py check` must pass in CI. `skills/cli-detector/tests/test_registry_consistency.py` cross-checks router vs registry.
- `./skills/prompt-executor/scripts/loop.py` — `run_cli_background()` (~line 560) and `run_cli_foreground()` (~line 682) build `full_cmd = base_command + [content]` for `stdin_mode == "arg"`, redirect stdout+stderr into the log file, and (foreground) return `{"status": "completed", "exit_code": ...}`; `check_completion_marker()` (~line 238) scans that log for `<verification>VERIFICATION_COMPLETE</verification>` / `NEEDS_RETRY:`; `run_verification_loop()` (~line 900+) consumes `exit_code` and marker results.
- `./skills/prompt-executor/scripts/sandbox.py` — `_is_agy_command()`, `_agy_auth_bind_file()`, `_agy_auth_preflight()` (runs `agy models` inside bwrap), and `build_bwrap_args()`. Sandbox binds only the OAuth token read-only on a tmpfs over `~/.gemini/antigravity-cli/`.
- `./skills/config-reader/scripts/config.py` — `KNOWN_KEYS` list (~line 25) and `<daplug_config>` parsing; new keys must be readable via `config.py get <key>`.
- `./skills/prompt-executor/scripts/executor.py` — CLI argparse (~line 590), `prompt_info["cli_command"]` preview, log path creation under `cli_logs_dir`.
- Tests: `./skills/prompt-executor/tests/` (`test_executor_variants.py`, `test_loop_verification.py`, `test_sandbox.py`, `test_sandbox_agy_integration.py`, `test_executor_logging.py`) and `./skills/cli-detector/tests/` (`test_router.py`, `test_registry_consistency.py`). Follow the existing pytest style there.

Installed CLI: `agy` at `/root/.local/bin/agy`, expected version 1.1.19. The prompt author could not execute `agy` while writing this, so every claim below about agy flags is a requirement for YOU to verify first, not a fact to trust.
</context>

<research>
Before writing code, verify AGY's official 1.1.19 behavior on this host and record findings in your final summary:
1. `agy --version` — must report 1.1.19. If it does not, report the actual version; still implement against the documented flags but say so.
2. `agy --help` (and any sub-help that surfaces `--print` options). Capture the exact names, argument formats, and defaults for: `--print-timeout` (duration syntax such as `60m` — confirm accepted units and the default), `--output-format` (confirm `stream-json` is valid and what the alternatives are), and the exit code / final message agy emits when the print timeout fires vs when a turn ends in an error.
3. Run a short real probe (`agy --model "Gemini 3.7 Flash (High)" --dangerously-skip-permissions --print-timeout 2m --output-format stream-json --print "Reply with the single word PONG"`) from a scratch dir, capture stdout, and derive the actual stream-json line shapes: the event type field, how progress/tool events look, the terminal result event, where `conversation_id` and `status` (or their real field names) appear, and how the assistant's final text is carried. Use that captured output as the basis for test fixtures — do not invent a schema.
4. Confirm whether agy accepts the prompt as the value immediately following `--print` (current daplug assumption) so that any flag placed after `--print` would be swallowed as the prompt. This is why the argv-order requirement below exists.
Thoroughly analyze the results before designing the parser; if reality differs from the requirements below, implement against reality and document the delta in your final summary.
</research>

<requirements>
1. Configuration
   - Add `agy_print_timeout` to `<daplug_config>` (default `60m`). Wire through `config.py` `KNOWN_KEYS`, the config-reader status/get output, and the executor so `_build_agy_command()` and the router builder emit the configured value. Accept agy's duration syntax verbatim; validate only that it is non-empty.
   - Add `agy_inactivity_timeout` (default: disabled) with a warning-then-terminate semantic independent of the total-runtime `--print-timeout`: if no stream-json event arrives for the configured interval, write a `[agy] inactivity warning ...` line to the log; if a second interval passes, terminate the process group and report status `agy_inactivity_timeout`. Implement this only where the architecture already reads the child's output (see Implementation); do not add it to code paths that only redirect stdout to a file handle unless you also convert them to a reader loop.
   - Expose both as executor CLI flags (`--agy-print-timeout`, `--agy-inactivity-timeout`) that override the config values. Keep names consistent everywhere.

2. Exact argv (the core fix)
   Every daplug-generated agy command must become, in this exact order:
   `agy --model "<display name>" --dangerously-skip-permissions --print-timeout <value> --output-format stream-json --print`
   and arg-mode then appends the prompt content as the final element, so the final process argv ends `... --print <prompt>`. Nothing may appear between `--print` and the prompt. Apply this identically in `models.py`, `router.py`, `manage-models.py`, and `scripts/models.json` (`command` arrays and `reference_cli` strings), then run `python3 scripts/manage-models.py generate` so the generated docs match; `python3 scripts/manage-models.py check` must pass.

3. Stream-json handling
   - Add a small pure module (e.g. `./skills/prompt-executor/scripts/agy_stream.py`) with a line-oriented parser: given one stdout line, return a typed event (progress / tool / assistant text / result / unknown), tolerate non-JSON and partial lines without raising, and extract `conversation_id` and terminal `status` using the real field names found in research.
   - In the AGY execution path, read the child's stdout line-by-line (instead of redirecting it straight into the log file), write every raw line to the same log file path daplug already uses (so `cli-logs` layout, filenames, and monitors are unchanged), and additionally write the human-readable assistant text so `check_completion_marker()` still finds `<verification>VERIFICATION_COMPLETE</verification>` and `NEEDS_RETRY:` markers exactly as before. Do not change `check_completion_marker()` behavior.
   - Persist `conversation_id` and terminal `status` into the returned execution dict and into the loop state (`~/.claude/loop-state/{n}.json`) iteration record.

4. Failure classification
   The execution result for AGY must distinguish at least: `completed` (terminal result event with success status), `agy_error` (terminal result with error status, or non-zero exit without timeout evidence), `agy_print_timeout` (agy's own timeout fired — detect via the exit code/message discovered in research), and `agy_inactivity_timeout` (daplug-side kill). `run_verification_loop()` must log a one-line human explanation for each and must not treat a timeout as a completed iteration.

5. Preservation guarantees (must be enforced by tests)
   - Legacy explicit `--cli gemini` commands (`gemini -y -m <id> -p`) are byte-for-byte unchanged.
   - Every non-AGY command (codex, opencode, claude, synthetic/local via opencode) is byte-for-byte unchanged, including `stdin_mode`, env, and sandbox wrapping.
   - Sandbox: `_is_agy_command()`, token bind, and `agy models` preflight keep working with the longer argv; bwrap wrapping preserves argv order and the prompt as last element.
   - Existing log file paths and loop log format remain unchanged apart from the new `[agy]` lines.

6. Scope discipline
   Touch the registry (`models.json`), generated docs, and cli-detector only where required to emit the new argv; do not refactor unrelated code. Do not add logging beyond the `[agy]` lines specified. Do not create documentation files; update only the generated regions plus the `<daplug_config>` key examples in `CLAUDE.md`/`README.md` where a config key list already exists.
</requirements>

<implementation>
- Build the argv from one shared helper if practical (display name + timeout -> list) so `models.py`, `router.py`, and `manage-models.py` cannot drift; if the router must stay import-free of `models.py`, duplicate the literal but pin them together with a consistency test.
- Reader loop: `subprocess.Popen(..., stdout=PIPE, stderr=STDOUT, text=True, start_new_session=True)`, iterate lines, apply the inactivity timer non-blockingly (`selectors` on the pipe fd or a reader thread + queue). Kill with `os.killpg(process.pid, SIGTERM)` then `SIGKILL` after a short grace. `run_cli_background()` returns immediately today; keep that, and implement the reader/inactivity handling in `run_cli_foreground()` (the loop runner already runs foreground per iteration).
- Because `--print` consumes the next argv token as the prompt, `--print-timeout`/`--output-format` must precede `--print`; tests must assert index order, not just membership.
- Keep the parser free of I/O so it is unit-testable with fixture strings captured in research.
- For maximum efficiency, when you need to read several independent files or run several independent checks, do them in parallel rather than sequentially. After each tool result, reflect on whether it changes the plan before continuing.
</implementation>

<output>
Modify (relative to repo root):
- `./skills/prompt-executor/scripts/models.py` — agy argv with timeout + output format
- `./skills/cli-detector/scripts/router.py` — matching agy argv
- `./scripts/manage-models.py`, `./scripts/models.json` — registry argv/reference_cli, then regenerate docs
- `./skills/prompt-executor/scripts/agy_stream.py` — new stream-json parser (pure)
- `./skills/prompt-executor/scripts/loop.py` — AGY reader loop, failure classification, state persistence
- `./skills/prompt-executor/scripts/executor.py` — new flags, config plumbing
- `./skills/config-reader/scripts/config.py` — new known keys
- Generated docs via `manage-models.py generate` only
- Tests under `./skills/prompt-executor/tests/` and `./skills/cli-detector/tests/`
</output>

<review_corrections>
Independent review after the first implementation pass found two merge-blocking false-success paths and five follow-ups. Fix and test all of these before emitting `VERIFICATION_COMPLETE`:

1. `completed` must require BOTH exit code 0 AND a terminal AGY result event for which `agy_stream.is_success(...)` is true. Missing terminal events, unknown/non-success statuses (including CANCELLED), and nonzero exits must classify as `agy_error` unless already classified as print/inactivity timeout.
2. Verification-loop marker detection must be gated on `exec_status == "completed"`. A marker present in a timeout/error log must never complete the loop; persist the execution failure and retry/fail normally.
3. Reject an explicitly empty `agy_print_timeout` instead of silently replacing it with the default. Keep omission/default behavior at 60m.
4. Narrow print-timeout detection to the observed AGY signature `timeout waiting for response`; do not classify arbitrary network/API timeout text as `agy_print_timeout`.
5. Update existing configuration examples in CLAUDE.md and README.md with `agy_print_timeout` and optional `agy_inactivity_timeout`.
6. Remove unrelated `scripts/models.json` em-dash serialization churn.
7. Add a real-pipe reader-loop test proving warn then process-group termination and `agy_inactivity_timeout`, plus regression tests for both blocking false-success cases.
8. Preserve the already verified default AGY argv, explicit legacy `--cli gemini` argv, and all non-AGY routes.

Run all three full suites and `python3 scripts/manage-models.py check` again. Do not commit, push, version-bump, tag, release, or modify files outside this worktree.
</review_corrections>

<verification>
**Unit tests** (all must pass):
```bash
cd skills/prompt-executor && python3 -m pytest tests/ -v
cd ../cli-detector && python3 -m pytest tests/ -v
cd ../config-reader && python3 -m pytest tests/ -v
cd ../.. && python3 scripts/manage-models.py check
python3 skills/prompt-executor/scripts/executor.py 009 --model gemini              # info mode: shows new argv
python3 skills/prompt-executor/scripts/executor.py 009 --model gemini --cli gemini # legacy argv unchanged
```

Create tests for:
- [ ] Exact argv: `get_cli_info("gemini")`, `("agy")`, `("gemini37-low")` and router `resolve_model` produce the exact list with `--print-timeout <v>` and `--output-format stream-json` at the correct indices and `--print` last; configured `agy_print_timeout` honored; default `60m`.
- [ ] Prompt placement: the launched argv (mock `subprocess.Popen` in `run_cli_foreground`/`run_cli_background`) ends with `["--print", <content>]` with no token between them; also under bwrap wrapping.
- [ ] Stream parsing: fixture lines from the real probe parse into progress/tool/result events; `conversation_id` and `status` extracted; malformed and non-JSON lines tolerated; assistant text containing `<verification>VERIFICATION_COMPLETE</verification>` reaches the log so `check_completion_marker()` returns found.
- [ ] Timeout/inactivity: a fake child emitting nothing triggers the warning line then termination with `agy_inactivity_timeout`; a fake child exiting with agy's timeout signature yields `agy_print_timeout`; error status yields `agy_error`; the loop marks none of these as completed.
- [ ] Sandbox: `_is_agy_command()` true for the new argv; `build_bwrap_args` keeps the prompt as final element; `_agy_auth_preflight` still probes `agy models`.
- [ ] Loop: iteration record contains `conversation_id`/`status`; existing loop tests stay green.
- [ ] Legacy regression: `--cli gemini` argv equals `["gemini","-y","-m","gemini-3.7-flash","-p"]` exactly; parametrize over every non-AGY shorthand in the registry and assert its command equals a literal expected list stored in the test.

Before declaring complete:
- Run the live probe once more with the daplug-built argv (e.g. `executor.py <n> --model gemini --run --no-sandbox` against a trivial scratch prompt) and confirm the log contains stream-json lines plus the plain assistant text.
- `git status` shows only intended files; no version bump in `.claude-plugin/plugin.json`; no new commits or tags.
</verification>

<success_criteria>
- All listed test suites and `manage-models.py check` pass.
- Default AGY argv is exactly `agy --model <display> --dangerously-skip-permissions --print-timeout 60m --output-format stream-json --print <prompt>`, configurable via `agy_print_timeout`.
- Logs still work with existing monitors and loop completion-marker detection.
- Execution results distinguish `completed`, `agy_error`, `agy_print_timeout`, `agy_inactivity_timeout` and preserve `conversation_id`/`status`.
- Legacy `--cli gemini` and all non-AGY commands unchanged byte-for-byte.
- Final summary states the observed `agy --version`, the verified flag semantics, and any deviations from this prompt.
</success_criteria>
