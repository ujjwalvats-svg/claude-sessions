"""Open sessions in new terminal tabs and bring running sessions to the front (macOS)."""

import os
import shlex
import subprocess

APPLE_TERMINAL = "Apple_Terminal"
GHOSTTY = "ghostty"
TAB_TERMINALS = frozenset({APPLE_TERMINAL, GHOSTTY})

# A new Terminal.app tab can only be made by pressing cmd-T through System Events, which
# needs Accessibility permission. Without it, fall back to a new window.
_TERMINAL_OPEN = """
on run argv
    set cmd to item 1 of argv
    tell application "Terminal" to activate
    try
        tell application "System Events" to keystroke "t" using command down
        delay 0.3
        tell application "Terminal" to do script cmd in front window
        return "tab"
    on error
        tell application "Terminal" to do script cmd
        return "window"
    end try
end run
"""

_GHOSTTY_OPEN = """
on run argv
    tell application "Ghostty"
        set cfg to new surface configuration
        set initial working directory of cfg to item 1 of argv
        set initial input of cfg to (item 2 of argv) & linefeed
        if (count of windows) > 0 then
            new tab in front window with configuration cfg
        else
            new window with configuration cfg
        end if
        activate
    end tell
    return "tab"
end run
"""

_TERMINAL_FOCUS = """
on run argv
    set target to item 1 of argv
    tell application "Terminal"
        repeat with w in windows
            repeat with t in tabs of w
                if tty of t is target then
                    set selected of t to true
                    set index of w to 1
                    activate
                    return "found"
                end if
            end repeat
        end repeat
    end tell
    return "missing"
end run
"""


class TerminalError(Exception):
    """The terminal app could not be scripted."""


def current_terminal() -> str:
    """Return the terminal app this process runs in, as reported by ``TERM_PROGRAM``."""
    return os.environ.get("TERM_PROGRAM", "")


def _osascript(script: str, *args: str) -> str:
    result = subprocess.run(
        ["osascript", "-e", script, *args], capture_output=True, text=True, check=False
    )
    if result.returncode != 0:
        raise TerminalError(f"osascript failed: {result.stderr.strip()}")
    return result.stdout.strip()


def resume_command(cwd: str, session_id: str) -> str:
    """Shell command that resumes ``session_id`` from its folder."""
    return f"cd {shlex.quote(cwd)} && claude --resume {shlex.quote(session_id)}"


def open_in_new_tab(terminal: str, cwd: str, session_id: str) -> str:
    """Resume a session in a new tab of ``terminal``.

    Returns:
        ``"tab"``, or ``"window"`` when Terminal.app lacks Accessibility permission.

    Raises:
        TerminalError: The terminal is not supported or refused the script.

    """
    if terminal == APPLE_TERMINAL:
        return _osascript(_TERMINAL_OPEN, resume_command(cwd, session_id))
    if terminal == GHOSTTY:
        return _osascript(_GHOSTTY_OPEN, cwd, f"claude --resume {shlex.quote(session_id)}")
    raise TerminalError(
        f"Opening in a new tab works in Terminal.app and Ghostty, not '{terminal or 'unknown'}'."
    )


def tty_of(pid: int) -> str:
    """Return the ``/dev/tty...`` path of a process, or "" if it has none."""
    result = subprocess.run(
        ["ps", "-o", "tty=", "-p", str(pid)], capture_output=True, text=True, check=False
    )
    tty = result.stdout.strip()
    return f"/dev/{tty}" if tty and tty != "??" else ""


def focus_tab(terminal: str, pid: int) -> bool:
    """Bring the tab running ``pid`` to the front; return False if it cannot be found."""
    tty = tty_of(pid)
    if terminal != APPLE_TERMINAL or not tty:
        return False
    return _osascript(_TERMINAL_FOCUS, tty) == "found"
