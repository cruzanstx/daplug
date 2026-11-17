"""No-Google policy guard (TLDRHQ / youtubesummaries) enforced inside the executor."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.append(str(SCRIPT_DIR))

import executor  # noqa: E402
import google_guard  # noqa: E402
from models import MODEL_REGISTRY_BY_NAME  # noqa: E402


def _first_model(predicate):
    for name, entry in MODEL_REGISTRY_BY_NAME.items():
        if predicate(entry):
            return name
    pytest.skip("registry has no matching model")


AGY_DEFAULT_MODEL = _first_model(lambda m: m["default_cli"] == "agy")
GOOGLE_ROUTED_MODEL = _first_model(lambda m: (m.get("routing") or {}).get("google"))
NON_GOOGLE_MODEL = "codex"


def _git(*args, cwd):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True)


def make_repo(parent: Path, name: str, origin: str | None = None) -> Path:
    repo = parent / name
    (repo / "prompts").mkdir(parents=True)
    (repo / "prompts" / "001-sample-task.md").write_text("# Sample task\n\nDo the thing.\n")
    _git("init", "-q", cwd=repo)
    if origin:
        _git("remote", "add", "origin", origin, cwd=repo)
    return repo


@pytest.fixture()
def harness(tmp_path, monkeypatch):
    """Patch executor side effects so tests can assert nothing was created."""
    logs_dir = tmp_path / "cli-logs"
    calls = {"worktree": 0, "cli_info": []}

    def fake_create_worktree(*_args, **_kwargs):
        calls["worktree"] += 1
        raise AssertionError("create_worktree must not run for a refused route")

    def fake_get_cli_info(model, **kwargs):
        calls["cli_info"].append((model, kwargs.get("cli_override")))
        return {
            "command": ["codex", "exec"],
            "display": f"fake {model}",
            "env": {},
            "stdin_mode": "dash",
            "selected_cli": calls.get("selected_cli", "codex"),
            "variant": None,
        }

    monkeypatch.delenv(google_guard.NO_GOOGLE_ENV, raising=False)
    monkeypatch.setattr(executor, "get_cli_logs_dir", lambda _repo_root: logs_dir)
    monkeypatch.setattr(executor, "create_worktree", fake_create_worktree)
    monkeypatch.setattr(executor, "get_cli_info", fake_get_cli_info)
    monkeypatch.setattr(executor, "_moa_cli_info", lambda model, *_a, cli_override=None, **_k: (
        fake_get_cli_info(model, cli_override=cli_override), None, False))

    def run(repo: Path, *argv):
        monkeypatch.setattr(executor, "get_repo_root", lambda: repo)
        monkeypatch.setattr(sys, "argv", ["executor.py", "001", *argv])
        executor.main()

    calls["run"] = run
    calls["logs_dir"] = logs_dir
    return calls


def assert_refused(harness, capsys, repo, *argv):
    with pytest.raises(SystemExit) as excinfo:
        harness["run"](repo, *argv)
    assert excinfo.value.code == google_guard.REFUSAL_EXIT_CODE
    captured = capsys.readouterr()
    assert "REFUSED" in captured.err
    payload = json.loads(captured.out)
    assert payload["refused"] == "no_google_policy"
    assert not harness["logs_dir"].exists(), "no log dir may be created before refusal"
    assert harness["worktree"] == 0
    return captured


# --- blocked -----------------------------------------------------------------

def test_blocked_on_repo_path_match(tmp_path, harness, capsys):
    repo = make_repo(tmp_path, "tldrhq-web")
    captured = assert_refused(harness, capsys, repo, "--model", GOOGLE_ROUTED_MODEL, "--run")
    assert "repo path" in captured.err
    assert harness["cli_info"] == [], "CLI preflight must not run before the guard"


def test_blocked_on_repo_path_match_case_insensitive(tmp_path, harness, capsys):
    repo = make_repo(tmp_path, "TLDRHQ")
    assert_refused(harness, capsys, repo, "--model", GOOGLE_ROUTED_MODEL, "--run")


def test_blocked_on_origin_url_match(tmp_path, harness, capsys):
    repo = make_repo(tmp_path, "app", origin="git@github.com:someone/youtube_summaries.git")
    captured = assert_refused(harness, capsys, repo, "--model", GOOGLE_ROUTED_MODEL, "--run")
    assert "origin URL" in captured.err


def test_blocked_on_cli_agy_with_non_google_model(tmp_path, harness, capsys):
    repo = make_repo(tmp_path, "youtubesummaries")
    captured = assert_refused(harness, capsys, repo, "--model", NON_GOOGLE_MODEL, "--cli", "agy", "--run")
    assert "--cli agy" in captured.err


@pytest.mark.parametrize("cli", ["gemini", "antigravity"])
def test_blocked_on_other_google_cli_spellings(tmp_path, harness, capsys, cli):
    repo = make_repo(tmp_path, "tldrhq")
    assert_refused(harness, capsys, repo, "--model", NON_GOOGLE_MODEL, "--cli", cli, "--run")


def test_blocked_on_model_with_default_cli_agy(tmp_path, harness, capsys):
    repo = make_repo(tmp_path, "tldrhq")
    assert_refused(harness, capsys, repo, "--model", AGY_DEFAULT_MODEL, "--run")


def test_blocked_on_model_with_routing_google(tmp_path, harness, capsys):
    repo = make_repo(tmp_path, "tldrhq")
    assert_refused(harness, capsys, repo, "--model", GOOGLE_ROUTED_MODEL, "--run")


def test_blocked_in_preview_mode(tmp_path, harness, capsys):
    """No --run: the preview/info path must refuse too."""
    repo = make_repo(tmp_path, "tldrhq")
    assert_refused(harness, capsys, repo, "--model", GOOGLE_ROUTED_MODEL)


def test_blocked_before_worktree_creation(tmp_path, harness, capsys):
    repo = make_repo(tmp_path, "tldrhq")
    assert_refused(harness, capsys, repo, "--model", GOOGLE_ROUTED_MODEL, "--worktree", "--run", "--loop")


def test_blocked_when_any_moa_entry_is_google(tmp_path, harness, capsys):
    repo = make_repo(tmp_path, "tldrhq")
    assert_refused(harness, capsys, repo, "--moa", f"{NON_GOOGLE_MODEL},{GOOGLE_ROUTED_MODEL}", "--run")


def test_blocked_when_cwd_points_into_protected_repo(tmp_path, harness, capsys):
    neutral = make_repo(tmp_path, "neutral")
    protected = make_repo(tmp_path, "youtube-summaries")
    assert_refused(harness, capsys, neutral, "--model", GOOGLE_ROUTED_MODEL, "--cwd", str(protected))


def test_blocked_when_router_resolves_to_google_cli(tmp_path, harness, capsys):
    repo = make_repo(tmp_path, "tldrhq")
    harness["selected_cli"] = "agy"
    captured = assert_refused(harness, capsys, repo, "--model", NON_GOOGLE_MODEL, "--run")
    assert "resolved" in captured.err


def test_invalid_regex_fails_closed(tmp_path, harness, capsys, monkeypatch):
    repo = make_repo(tmp_path, "anything")
    monkeypatch.setenv(google_guard.NO_GOOGLE_ENV, "(unclosed")
    captured = assert_refused(harness, capsys, repo, "--model", GOOGLE_ROUTED_MODEL)
    assert "not a valid regex" in captured.err


# --- allowed -----------------------------------------------------------------

def test_allowed_google_route_in_non_matching_repo(tmp_path, harness, capsys):
    repo = make_repo(tmp_path, "other-project", origin="https://github.com/someone/other-project.git")
    harness["run"](repo, "--model", GOOGLE_ROUTED_MODEL)
    payload = json.loads(capsys.readouterr().out)
    assert payload["model"] == GOOGLE_ROUTED_MODEL
    assert harness["cli_info"] == [(GOOGLE_ROUTED_MODEL, None)]


def test_allowed_non_google_route_in_protected_repo(tmp_path, harness, capsys):
    repo = make_repo(tmp_path, "tldrhq")
    harness["run"](repo, "--model", NON_GOOGLE_MODEL)
    payload = json.loads(capsys.readouterr().out)
    assert payload["model"] == NON_GOOGLE_MODEL


def test_allowed_when_override_is_empty(tmp_path, harness, capsys, monkeypatch):
    repo = make_repo(tmp_path, "tldrhq", origin="git@github.com:someone/tldrhq.git")
    monkeypatch.setenv(google_guard.NO_GOOGLE_ENV, "")
    harness["run"](repo, "--model", GOOGLE_ROUTED_MODEL, "--cli", "agy")
    payload = json.loads(capsys.readouterr().out)
    assert payload["model"] == GOOGLE_ROUTED_MODEL


def test_custom_pattern_replaces_default(tmp_path, harness, capsys, monkeypatch):
    monkeypatch.setenv(google_guard.NO_GOOGLE_ENV, "secret-repo")
    harness["run"](make_repo(tmp_path, "tldrhq"), "--model", GOOGLE_ROUTED_MODEL)
    capsys.readouterr()
    harness["logs_dir"].rmdir()  # created by the allowed run above
    assert_refused(harness, capsys, make_repo(tmp_path, "secret-repo"), "--model", GOOGLE_ROUTED_MODEL)


# --- unit: route definition ----------------------------------------------------

FAKE_REGISTRY = {
    "agy-only": {"default_cli": "agy", "routing": {"google": False}},
    "google-flag": {"default_cli": "opencode", "routing": {"google": True}},
    "gemini-cli": {"default_cli": "gemini", "routing": {}},
    "plain": {"default_cli": "codex", "routing": {"google": False}},
}


@pytest.mark.parametrize(
    "model,cli,expected",
    [
        ("agy-only", None, "agy CLI by default"),
        ("google-flag", None, "routing.google=true"),
        ("gemini-cli", None, "gemini CLI by default"),
        ("plain", "agy", "--cli agy"),
        ("plain", "Antigravity", "--cli agy"),
        ("missing", None, "not in the daplug registry"),
        ("plain", None, None),
        ("plain", "opencode", None),
    ],
)
def test_google_route_reason(model, cli, expected):
    reason = google_guard.google_route_reason(model, cli, FAKE_REGISTRY)
    if expected is None:
        assert reason is None
    else:
        assert expected in reason


def test_pattern_defaults_and_override():
    assert google_guard.protected_repo_pattern({}) == google_guard.DEFAULT_NO_GOOGLE_REPOS
    assert google_guard.protected_repo_pattern({google_guard.NO_GOOGLE_ENV: ""}) is None
    assert google_guard.protected_repo_pattern({google_guard.NO_GOOGLE_ENV: "  "}) is None
    assert google_guard.protected_repo_pattern({google_guard.NO_GOOGLE_ENV: "foo"}) == "foo"


@pytest.mark.parametrize("name", ["tldrhq", "youtubesummaries", "youtube-summaries", "youtube_summaries", "my-TLDRHQ-fork"])
def test_default_pattern_matches_protected_names(name):
    assert google_guard.find_protected_match([f"/srv/{name}"], google_guard.DEFAULT_NO_GOOGLE_REPOS)


# --- end to end: direct executor.py invocation ----------------------------------

def test_direct_executor_invocation_refuses(tmp_path):
    repo = make_repo(tmp_path, "tldrhq")
    env = {k: v for k, v in os.environ.items() if k != google_guard.NO_GOOGLE_ENV}
    env["HOME"] = str(tmp_path / "home")
    result = subprocess.run(
        [sys.executable, str(SCRIPT_DIR / "executor.py"), "001", "--model", GOOGLE_ROUTED_MODEL, "--run"],
        cwd=repo,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == google_guard.REFUSAL_EXIT_CODE, result.stderr
    assert "REFUSED" in result.stderr
    assert not (tmp_path / "home" / ".claude" / "cli-logs").exists()
