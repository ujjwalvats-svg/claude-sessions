import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from claude_sessions import terminal

needs_macos = pytest.mark.skipif(sys.platform != "darwin", reason="AppleScript is macOS only")


def test_resume_command_quotes_folder() -> None:
    assert terminal.resume_command("/a b/it's", "id-1") == (
        "cd '/a b/it'\"'\"'s' && claude --resume id-1"
    )


def test_unsupported_terminal_is_refused_with_a_reason() -> None:
    with pytest.raises(terminal.TerminalError, match=r"Terminal\.app and Ghostty"):
        terminal.open_in_new_tab("vscode", "/tmp", "id")


def test_terminal_tab_is_opened_with_the_resume_command(monkeypatch) -> None:
    calls: list[tuple[str, ...]] = []
    monkeypatch.setattr(terminal, "_osascript", lambda *a: calls.append(a) or "tab")

    assert terminal.open_in_new_tab(terminal.APPLE_TERMINAL, "/repo", "id-1") == "tab"
    assert calls[0][1:] == ("cd /repo && claude --resume id-1",)


def test_ghostty_tab_gets_folder_and_command_separately(monkeypatch) -> None:
    calls: list[tuple[str, ...]] = []
    monkeypatch.setattr(terminal, "_osascript", lambda *a: calls.append(a) or "tab")

    terminal.open_in_new_tab(terminal.GHOSTTY, "/repo", "id-1")
    assert calls[0][1:] == ("/repo", "claude --resume id-1")


def test_osascript_failure_is_reported() -> None:
    if shutil.which("osascript") is None:
        pytest.skip("osascript not available")
    with pytest.raises(terminal.TerminalError, match="osascript failed"):
        terminal._osascript("error 42")


def test_tty_of_a_process_without_terminal_is_empty() -> None:
    proc = subprocess.Popen(["sleep", "5"], stdin=subprocess.DEVNULL, start_new_session=True)
    try:
        assert terminal.tty_of(proc.pid) == ""
    finally:
        proc.kill()
        proc.wait()


def test_focus_only_works_in_terminal_app(monkeypatch) -> None:
    monkeypatch.setattr(terminal, "tty_of", lambda _pid: "/dev/ttys001")
    monkeypatch.setattr(terminal, "_osascript", lambda *_a: "found")
    assert terminal.focus_tab(terminal.APPLE_TERMINAL, 1)
    assert not terminal.focus_tab(terminal.GHOSTTY, 1)


def test_focus_reports_missing_tab(monkeypatch) -> None:
    monkeypatch.setattr(terminal, "tty_of", lambda _pid: "/dev/ttys001")
    monkeypatch.setattr(terminal, "_osascript", lambda *_a: "missing")
    assert not terminal.focus_tab(terminal.APPLE_TERMINAL, 1)


@needs_macos
@pytest.mark.parametrize(
    ("script", "app"),
    [
        (terminal._TERMINAL_OPEN, "/System/Applications/Utilities/Terminal.app"),
        (terminal._TERMINAL_FOCUS, "/System/Applications/Utilities/Terminal.app"),
        (terminal._GHOSTTY_OPEN, "/Applications/Ghostty.app"),
    ],
)
def test_applescripts_compile_against_the_app_dictionary(
    script: str, app: str, tmp_path: Path
) -> None:
    if not Path(app).exists():
        pytest.skip(f"{app} not installed")
    result = subprocess.run(
        ["osacompile", "-o", str(tmp_path / "s.scpt"), "-e", script],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
