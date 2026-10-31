from pathlib import Path

import pytest

from claude_sessions.sessions import Running, Session
from claude_sessions.state import State
from claude_sessions.view import (
    age,
    fit,
    format_row,
    preview,
    recent_messages,
    short_path,
    title_of,
    visible_sessions,
)
from tests.conftest import assistant, user, write_transcript


def make(session_id: str, updated: float = 0, **fields: str) -> Session:
    base = {
        "path": "/nowhere.jsonl",
        "cwd": "/work",
        "branch": "",
        "custom_title": "",
        "ai_title": "",
        "last_prompt": "",
        "first_prompt": "",
    }
    return Session(id=session_id, updated=updated, **(base | fields))


LIVE = Running(pid=1, status="idle", rss_mb=150)


def test_order_is_pinned_then_running_then_most_recent() -> None:
    sessions = [make("old", 1), make("new", 3), make("live", 2), make("pin", 0)]
    state = State(pinned={"pin"})

    shown = visible_sessions(sessions, state, {"live": LIVE}, show_archived=False)

    assert [s.id for s in shown] == ["pin", "live", "new", "old"]


def test_archived_sessions_are_hidden_unless_running_or_requested() -> None:
    sessions = [make("arch"), make("arch-live"), make("normal")]
    state = State(archived={"arch", "arch-live"})
    running = {"arch-live": LIVE}

    default = visible_sessions(sessions, state, running, show_archived=False)
    everything = visible_sessions(sessions, state, running, show_archived=True)

    assert {s.id for s in default} == {"arch-live", "normal"}
    assert {s.id for s in everything} == {"arch", "arch-live", "normal"}


def test_title_prefers_label_then_names_then_prompts() -> None:
    session = make("s", custom_title="renamed", ai_title="AI", last_prompt="last")
    assert title_of(session, State(labels={"s": "my label"})) == "my label"
    assert title_of(session, State()) == "renamed"
    assert title_of(make("s", ai_title="AI", last_prompt="last"), State()) == "AI"
    assert title_of(make("s", first_prompt="  multi\nline  "), State()) == "multi line"
    assert title_of(make("s"), State()) == "(no prompt)"


@pytest.mark.parametrize(
    ("seconds", "expected"),
    [(0, "now"), (59, "now"), (60, "1m"), (7200, "2h"), (86400 * 3, "3d"), (86400 * 65, "2mo")],
)
def test_age(seconds: int, expected: str) -> None:
    assert age(1000.0, 1000.0 + seconds) == expected


def test_age_in_the_future_is_now() -> None:
    assert age(2000.0, 1000.0) == "now"


def test_fit_pads_and_truncates() -> None:
    assert fit("abc", 5) == "abc  "
    assert fit("abcdefgh", 5) == "abcd…"
    assert fit("/a/b/project", 6, keep_end=True) == "…oject"


def test_short_path_only_replaces_whole_home_prefix() -> None:
    assert short_path("/Users/me", "/Users/me") == "~"
    assert short_path("/Users/me/repo", "/Users/me") == "~/repo"
    assert short_path("/Users/meow", "/Users/me") == "/Users/meow"


def test_row_starts_with_id_and_shows_memory_for_running() -> None:
    row = format_row(make("abc", 0, branch="HEAD"), State(), {"abc": LIVE}, 0, "/home")
    session_id, rest = row.split("\t", 1)
    assert session_id == "abc"
    assert "150MB idle" in rest
    assert "HEAD" not in rest


def test_recent_messages_keeps_only_conversation_text(tmp_path: Path) -> None:
    path = write_transcript(
        tmp_path / "s.jsonl",
        [
            user("first question"),
            assistant("first answer"),
            {"type": "user", "message": {"content": [{"type": "tool_result", "content": "x"}]}},
            user("<command-name>/clear</command-name>"),
            user("second question"),
        ],
        tail="{half",
    )

    assert recent_messages(path, limit=2) == [
        ("assistant", "first answer"),
        ("user", "second question"),
    ]


def test_recent_messages_reads_only_the_tail_of_big_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("claude_sessions.view.PREVIEW_TAIL_BYTES", 200)
    path = write_transcript(
        tmp_path / "s.jsonl", [user("x" * 300), user("old"), assistant("newest")]
    )

    assert recent_messages(path) == [("user", "old"), ("assistant", "newest")]


def test_preview_warns_when_folder_is_gone(tmp_path: Path) -> None:
    path = write_transcript(tmp_path / "s.jsonl", [user("hello")])
    session = make("s", path=str(path), cwd=str(tmp_path / "deleted"), first_prompt="hello")

    text = preview(session, State(pinned={"s"}), {}, "/home")

    assert "folder no longer exists" in text
    assert "flags:   pinned" in text
    assert "status:  stopped" in text
    assert "[user]\nhello" in text
