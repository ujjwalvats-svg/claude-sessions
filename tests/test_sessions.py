import json
import os
import signal
from pathlib import Path

from claude_sessions.sessions import load_sessions, read_session, running_sessions
from tests.conftest import register_running, user, wait_gone, write_transcript


def test_read_session_collects_titles_folder_and_branch(tmp_path: Path) -> None:
    path = write_transcript(
        tmp_path / "proj" / "abc.jsonl",
        [
            user("<command-name>/clear</command-name>", cwd="/repo", branch="main"),
            user("ignored meta", isMeta=True),
            user("fix the login bug", branch="main"),
            {"type": "custom-title", "customTitle": "old name"},
            {"type": "ai-title", "aiTitle": "Login bug fix"},
            {"type": "last-prompt", "lastPrompt": "run the tests"},
            {"type": "custom-title", "customTitle": "login-fix"},
            user("next", branch="feature/login"),
        ],
    )

    session = read_session(path, mtime=123.0)

    assert session is not None
    assert session.id == "abc"
    assert session.cwd == "/repo"
    assert session.branch == "feature/login"
    assert session.custom_title == "login-fix"
    assert session.ai_title == "Login bug fix"
    assert session.last_prompt == "run the tests"
    assert session.first_prompt == "fix the login bug"
    assert session.updated == 123.0


def test_read_session_without_folder_is_skipped(tmp_path: Path) -> None:
    path = write_transcript(tmp_path / "p" / "x.jsonl", [{"type": "mode"}])
    assert read_session(path, 0) is None


def test_read_session_tolerates_half_written_last_line(tmp_path: Path) -> None:
    path = write_transcript(
        tmp_path / "p" / "x.jsonl", [user("hello")], tail='{"type":"custom-title","custo'
    )
    session = read_session(path, 0)
    assert session is not None
    assert session.first_prompt == "hello"


def test_read_session_ignores_wrongly_typed_fields(tmp_path: Path) -> None:
    path = write_transcript(
        tmp_path / "p" / "x.jsonl",
        [user("hello"), {"type": "ai-title", "aiTitle": 42}, {"type": "user", "message": "x"}],
    )
    session = read_session(path, 0)
    assert session is not None
    assert session.ai_title == ""


def test_load_sessions_picks_up_changes_after_caching(tmp_path: Path) -> None:
    projects, cache = tmp_path / "projects", tmp_path / "cache.json"
    path = write_transcript(projects / "p" / "s1.jsonl", [user("first")])
    write_transcript(projects / "p" / "empty.jsonl", [{"type": "mode"}])
    assert [s.first_prompt for s in load_sessions(projects, cache)] == ["first"]

    write_transcript(path, [user("first"), {"type": "custom-title", "customTitle": "renamed"}])
    os.utime(path, (1, 1))

    assert [s.custom_title for s in load_sessions(projects, cache)] == ["renamed"]


def test_load_sessions_rebuilds_a_damaged_cache(tmp_path: Path) -> None:
    projects, cache = tmp_path / "projects", tmp_path / "cache.json"
    write_transcript(projects / "p" / "s1.jsonl", [user("first")])
    cache.write_text("{not json")

    assert [s.id for s in load_sessions(projects, cache)] == ["s1"]
    assert json.loads(cache.read_text())["version"] == 1


def test_running_sessions_reports_live_claude_processes_only(env: Path, fake_claude: int) -> None:
    register_running(env, fake_claude, "live-session")
    register_running(env, os.getpid(), "python-not-claude")
    (env / "sessions" / "torn.json").write_text("{")

    running = running_sessions(env / "sessions")

    assert set(running) == {"live-session"}
    assert running["live-session"].pid == fake_claude
    assert running["live-session"].status == "idle"


def test_running_sessions_ignores_exited_processes(env: Path, fake_claude: int) -> None:
    register_running(env, fake_claude, "gone")
    os.kill(fake_claude, signal.SIGKILL)
    assert wait_gone(fake_claude)

    assert running_sessions(env / "sessions") == {}
