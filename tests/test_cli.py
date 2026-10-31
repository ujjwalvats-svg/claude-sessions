import json
import shutil
import subprocess
from pathlib import Path

import pytest

from claude_sessions.cli import (
    CliError,
    Context,
    Paths,
    load_context,
    main,
    resolve,
    stop_process,
)
from tests.conftest import is_alive, register_running, user, wait_gone, write_transcript

SESSION_A = "aaaa1111-0000-0000-0000-000000000000"
SESSION_B = "aaaa2222-0000-0000-0000-000000000000"


@pytest.fixture
def two_sessions(env: Path, tmp_path: Path) -> Path:
    workdir = tmp_path / "repo"
    workdir.mkdir()
    write_transcript(env / "projects" / "p" / f"{SESSION_A}.jsonl", [user("A", cwd=str(workdir))])
    write_transcript(
        env / "projects" / "p" / f"{SESSION_B}.jsonl",
        [user("B", cwd=str(tmp_path / "deleted")), {"type": "custom-title", "customTitle": "bee"}],
    )
    return workdir


def listed(capsys: pytest.CaptureFixture[str], *flags: str) -> list[dict]:
    capsys.readouterr()
    assert main(["list", "--json", *flags]) == 0
    return json.loads(capsys.readouterr().out)


def by_id(rows: list[dict], session_id: str) -> dict:
    return next(row for row in rows if row["id"] == session_id)


def context() -> Context:
    return load_context(Paths.from_env())


def test_resolve_by_prefix_name_and_label(two_sessions: Path) -> None:
    assert resolve(context(), "aaaa1").id == SESSION_A
    assert resolve(context(), "bee").id == SESSION_B
    assert main(["label", "aaaa1", "order sync"]) == 0
    assert resolve(context(), "order sync").id == SESSION_A


def test_resolve_rejects_unknown_and_ambiguous(two_sessions: Path) -> None:
    with pytest.raises(CliError, match="No session matches"):
        resolve(context(), "zzz")
    with pytest.raises(CliError, match="matches 2 sessions"):
        resolve(context(), "aaaa")


def test_pin_archive_and_toggle(two_sessions: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["pin", "aaaa2"]) == 0
    assert [s["id"] for s in listed(capsys)] == [SESSION_B, SESSION_A]

    assert main(["archive", "aaaa2"]) == 0
    assert [s["id"] for s in listed(capsys)] == [SESSION_A]
    assert {s["id"] for s in listed(capsys, "--all")} == {SESSION_A, SESSION_B}

    assert main(["toggle", "archive", "aaaa2"]) == 0
    assert main(["toggle", "pin", "aaaa2"]) == 0
    assert "unpinned: bee" in capsys.readouterr().out
    rows = listed(capsys)
    assert [(s["pinned"], s["archived"]) for s in rows] == [(False, False), (False, False)]


def test_label_set_and_clear(two_sessions: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["label", "aaaa1", "  QA   for orders "]) == 0
    assert by_id(listed(capsys), SESSION_A)["title"] == "QA for orders"
    assert main(["label", "aaaa1", ""]) == 0
    assert by_id(listed(capsys), SESSION_A)["label"] == ""


def test_label_prompts_when_text_omitted(
    two_sessions: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("builtins.input", lambda _prompt: "typed label")
    assert main(["label", "aaaa1"]) == 0
    assert by_id(listed(capsys), SESSION_A)["label"] == "typed label"


def test_errors_are_reported_without_traceback(
    two_sessions: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["open", "nothing-like-this"]) == 1
    assert capsys.readouterr().err.startswith("cs: No session matches")


def test_damaged_state_file_is_reported(env: Path, tmp_path: Path, capsys) -> None:
    state_file = tmp_path / "config" / "claude-sessions" / "state.json"
    state_file.parent.mkdir(parents=True)
    state_file.write_text("{oops")
    assert main(["list"]) == 1
    assert "Fix or delete it" in capsys.readouterr().err


def test_missing_claude_dir_is_reported(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "absent"))
    assert main(["list"]) == 1
    assert "does not exist" in capsys.readouterr().err


def test_open_refuses_when_folder_was_deleted(
    two_sessions: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["open", "bee"]) == 1
    assert "no longer exists" in capsys.readouterr().err


def test_open_resumes_in_the_session_folder(
    two_sessions: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[tuple[str, list[str], str]] = []
    monkeypatch.setattr("shutil.which", lambda name: f"/bin/{name}")
    monkeypatch.setattr("os.execv", lambda exe, argv: calls.append((exe, argv, str(Path.cwd()))))

    main(["open", "aaaa1"])

    assert calls == [("/bin/claude", ["claude", "--resume", SESSION_A], str(two_sessions))]


def test_open_running_session_asks_before_taking_it_over(
    two_sessions: Path,
    env: Path,
    fake_claude: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    register_running(env, fake_claude, SESSION_A)
    calls: list[list[str]] = []
    monkeypatch.setattr("os.execv", lambda _exe, argv: calls.append(argv))

    monkeypatch.setattr("builtins.input", lambda _prompt: "n")
    assert main(["open", "aaaa1"]) == 0
    assert calls == []
    assert is_alive(fake_claude)

    monkeypatch.setattr("builtins.input", lambda _prompt: "y")
    main(["open", "aaaa1"])
    assert wait_gone(fake_claude)
    assert calls == [["claude", "--resume", SESSION_A]]


def test_stop_frees_a_running_session(
    two_sessions: Path,
    env: Path,
    fake_claude: int,
    capsys: pytest.CaptureFixture[str],
) -> None:
    register_running(env, fake_claude, SESSION_A)
    assert by_id(listed(capsys), SESSION_A)["running"]["pid"] == fake_claude

    assert main(["stop", "aaaa1", "--yes"]) == 0
    assert wait_gone(fake_claude)
    assert "Stopped pid" in capsys.readouterr().out


def test_stop_declined_keeps_process(
    two_sessions: Path, env: Path, fake_claude: int, monkeypatch
) -> None:
    register_running(env, fake_claude, SESSION_A)
    monkeypatch.setattr("builtins.input", lambda _prompt: "")
    assert main(["stop", "aaaa1"]) == 0
    assert is_alive(fake_claude)


def test_stop_not_running_is_a_no_op(two_sessions: Path, capsys) -> None:
    assert main(["stop", "aaaa1", "--yes"]) == 0
    assert "Not running" in capsys.readouterr().out


def test_stop_refuses_to_kill_its_own_session(
    two_sessions: Path, env: Path, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    register_running(env, 4242, SESSION_A)
    monkeypatch.setattr("claude_sessions.sessions._live_claude_pids", lambda _p: {4242: 10})
    monkeypatch.setattr("claude_sessions.cli.ancestor_pids", lambda: {4242})
    assert main(["stop", "aaaa1", "--yes"]) == 1
    assert "/exit" in capsys.readouterr().err


def test_stop_process_gives_up_on_a_process_ignoring_sigterm() -> None:
    proc = subprocess.Popen(
        [
            "python3",
            "-c",
            "import signal,time; signal.signal(signal.SIGTERM, signal.SIG_IGN);"
            "print('ready', flush=True); time.sleep(30)",
        ],
        stdout=subprocess.PIPE,
        text=True,
    )
    try:
        assert proc.stdout is not None
        proc.stdout.readline()
        with pytest.raises(CliError, match="kill -9"):
            stop_process(proc.pid, timeout=0.3)
    finally:
        proc.kill()
        proc.wait()


@pytest.fixture
def fake_trash(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A stand-in for macOS ``trash`` that moves files aside and logs their paths."""
    bin_dir, bin_ = tmp_path / "fakebin", tmp_path / "fakebin" / "trash"
    bin_dir.mkdir()
    trash_dir = tmp_path / "Trash"
    trash_dir.mkdir()
    bin_.write_text(
        "#!/bin/sh\nfor f; do\n"
        f'  echo "$f" >> {trash_dir}/log\n'
        f'  mv "$f" "{trash_dir}/$(date +%s%N)-$RANDOM"\n'
        "done\n"
    )
    bin_.chmod(0o755)
    real_which = shutil.which
    monkeypatch.setattr(
        "shutil.which", lambda name: str(bin_) if name == "trash" else real_which(name)
    )
    return trash_dir


def trashed(trash_dir: Path) -> list[str]:
    log = trash_dir / "log"
    return log.read_text().splitlines() if log.exists() else []


def test_delete_moves_every_session_file_to_trash_and_forgets_state(
    two_sessions: Path, env: Path, fake_trash: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (env / "projects" / "p" / SESSION_A).mkdir()
    (env / "file-history" / SESSION_A).mkdir(parents=True)
    (env / "session-env" / SESSION_A).mkdir(parents=True)
    assert main(["pin", "aaaa1"]) == 0
    assert main(["label", "aaaa1", "doomed"]) == 0

    assert main(["delete", "aaaa1", "--yes"]) == 0

    assert "Moved to Trash: doomed" in capsys.readouterr().out
    assert trashed(fake_trash) == [
        str(env / "projects" / "p" / f"{SESSION_A}.jsonl"),
        str(env / "projects" / "p" / SESSION_A),
        str(env / "file-history" / SESSION_A),
        str(env / "session-env" / SESSION_A),
    ]
    assert not (env / "projects" / "p" / f"{SESSION_A}.jsonl").exists()
    assert not (env / "file-history" / SESSION_A).exists()
    assert not (env / "session-env" / SESSION_A).exists()
    assert [s["id"] for s in listed(capsys, "--all")] == [SESSION_B]
    state = json.loads((env.parent / "config" / "claude-sessions" / "state.json").read_text())
    assert state == {"pinned": [], "archived": [], "labels": {}}


def test_delete_asks_first_and_no_keeps_the_session(
    two_sessions: Path, env: Path, fake_trash: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    questions: list[str] = []
    monkeypatch.setattr("builtins.input", lambda q: questions.append(q) or "n")

    assert main(["delete", "aaaa1"]) == 0

    assert "Delete 'A'?" in questions[0]
    assert (env / "projects" / "p" / f"{SESSION_A}.jsonl").exists()
    assert trashed(fake_trash) == []


def test_delete_refuses_a_running_session(
    two_sessions: Path, env: Path, fake_claude: int, fake_trash: Path, capsys
) -> None:
    register_running(env, fake_claude, SESSION_A)
    assert main(["delete", "aaaa1", "--yes"]) == 1
    assert "Stop it first" in capsys.readouterr().err
    assert (env / "projects" / "p" / f"{SESSION_A}.jsonl").exists()


def test_open_tab_hook_opens_and_reports_status(
    two_sessions: Path, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    opened: list[tuple[str, str, str]] = []
    monkeypatch.setenv("TERM_PROGRAM", "Apple_Terminal")
    monkeypatch.setattr(
        "claude_sessions.terminal.open_in_new_tab",
        lambda app, cwd, sid: opened.append((app, cwd, sid)) or "tab",
    )

    assert main(["open-tab", SESSION_A]) == 0

    assert opened == [("Apple_Terminal", str(two_sessions), SESSION_A)]
    out = capsys.readouterr().out.removesuffix("\n")
    assert out.startswith("reload(")
    assert out.endswith("+change-header-label: Opened 'A' in a new tab ")


def test_open_tab_hook_switches_to_a_running_session(
    two_sessions: Path, env: Path, fake_claude: int, monkeypatch, capsys
) -> None:
    register_running(env, fake_claude, SESSION_A)
    monkeypatch.setenv("TERM_PROGRAM", "Apple_Terminal")
    focused: list[int] = []
    monkeypatch.setattr(
        "claude_sessions.terminal.focus_tab", lambda _app, pid: focused.append(pid) or True
    )
    monkeypatch.setattr(
        "claude_sessions.terminal.open_in_new_tab",
        lambda *_a: pytest.fail("must not open a second copy"),
    )

    assert main(["open-tab", SESSION_A]) == 0

    assert focused == [fake_claude]
    assert "Switched to the tab running 'A'" in capsys.readouterr().out


def test_open_tab_hook_reports_errors_as_status(two_sessions: Path, capsys) -> None:
    assert main(["open-tab", SESSION_B]) == 0
    out = capsys.readouterr().out
    assert "change-header-label: ✗ Folder" in out
    assert "no longer exists" in out


def test_open_tab_mentions_accessibility_when_only_a_window_opened(
    two_sessions: Path, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    monkeypatch.setenv("TERM_PROGRAM", "Apple_Terminal")
    monkeypatch.setattr("claude_sessions.terminal.open_in_new_tab", lambda *_a: "window")
    assert main(["open", "aaaa1", "--tab"]) == 0
    assert "Accessibility" in capsys.readouterr().out


def test_toolbar_hook_prints_actions_for_the_clicked_word(capsys) -> None:
    assert main(["toolbar", "🗑", SESSION_A]) == 0
    assert f"delete {SESSION_A})+reload(" in capsys.readouterr().out


def test_errors_inside_the_picker_become_a_notice(
    two_sessions: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    shown: list[str] = []
    monkeypatch.setenv("FZF_PROMPT", "sessions> ")
    monkeypatch.setattr("claude_sessions.cli.notice", shown.append)
    assert main(["stop", "nothing-like-this"]) == 1
    assert shown and shown[0].startswith("No session matches")


@pytest.mark.parametrize("version", ["0.60.0 (brew)", "garbage"])
def test_picker_refuses_old_or_unknown_fzf(
    two_sessions: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys, version: str
) -> None:
    old = tmp_path / "oldbin" / "fzf"
    old.parent.mkdir()
    old.write_text(f"#!/bin/sh\necho '{version}'\n")
    old.chmod(0o755)
    monkeypatch.setenv("PATH", f"{old.parent}:/usr/bin:/bin")

    assert main([]) == 1
    err = capsys.readouterr().err
    assert "needs fzf 0.73.0 or newer" in err
    assert "brew upgrade fzf" in err
