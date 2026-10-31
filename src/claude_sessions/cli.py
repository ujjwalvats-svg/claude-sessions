"""``cs``: find, pin, archive, label, open, stop and delete Claude Code sessions."""

import argparse
import json
import os
import shlex
import shutil
import signal
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path

from claude_sessions import picker, terminal
from claude_sessions.dialog import confirm, notice
from claude_sessions.sessions import (
    Running,
    Session,
    ancestor_pids,
    load_sessions,
    running_sessions,
)
from claude_sessions.state import State, StateError, load_state, save_state
from claude_sessions.view import format_row, preview, short_path, title_of, visible_sessions

STOP_TIMEOUT_SECONDS = 5.0


class CliError(Exception):
    """A user-facing failure with an actionable message."""


@dataclass(frozen=True)
class Paths:
    """Filesystem locations the tool reads and writes."""

    claude_dir: Path
    state_file: Path
    cache_file: Path

    @classmethod
    def from_env(cls) -> "Paths":
        """Resolve paths, honouring ``CLAUDE_CONFIG_DIR`` and XDG base directories."""
        home = Path.home()
        claude_dir = Path(os.environ.get("CLAUDE_CONFIG_DIR") or home / ".claude")
        config = Path(os.environ.get("XDG_CONFIG_HOME") or home / ".config")
        cache = Path(os.environ.get("XDG_CACHE_HOME") or home / ".cache")
        return cls(
            claude_dir=claude_dir,
            state_file=config / "claude-sessions" / "state.json",
            cache_file=cache / "claude-sessions" / "index.json",
        )


@dataclass
class Context:
    """Everything a command needs, loaded once per invocation."""

    paths: Paths
    sessions: list[Session]
    state: State
    running: dict[str, Running]


def load_context(paths: Paths) -> Context:
    """Load sessions, user state and running processes."""
    projects = paths.claude_dir / "projects"
    if not projects.is_dir():
        raise CliError(f"No Claude Code sessions found: {projects} does not exist.")
    return Context(
        paths=paths,
        sessions=load_sessions(projects, paths.cache_file),
        state=load_state(paths.state_file),
        running=running_sessions(paths.claude_dir / "sessions"),
    )


def resolve(ctx: Context, ref: str) -> Session:
    """Find a session by id, unique id prefix, label or Claude session name."""
    exact = [s for s in ctx.sessions if s.id == ref]
    if exact:
        return exact[0]
    matches = [
        s
        for s in ctx.sessions
        if s.id.startswith(ref) or ref in (ctx.state.labels.get(s.id), s.custom_title)
    ]
    if not ref or not matches:
        raise CliError(f"No session matches '{ref}'. Run 'cs list' to see session ids.")
    if len(matches) > 1:
        options = "\n".join(f"  {s.id}  {title_of(s, ctx.state)}" for s in matches[:10])
        raise CliError(f"'{ref}' matches {len(matches)} sessions; be more specific:\n{options}")
    return matches[0]


def stop_process(pid: int, timeout: float = STOP_TIMEOUT_SECONDS) -> None:
    """Send SIGTERM to ``pid`` and wait for it to exit."""
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return
        time.sleep(0.1)
    raise CliError(f"Process {pid} is still running after {timeout:.0f}s. Try: kill -9 {pid}")


def _guard_not_self(live: Running) -> None:
    if live.pid in ancestor_pids():
        raise CliError("That is the session cs is running inside. Leave it with /exit instead.")


def cmd_list(paths: Paths, args: argparse.Namespace) -> int:
    """Print sessions as picker rows, or as JSON with ``--json``."""
    ctx = load_context(paths)
    in_archive_view = os.environ.get("FZF_PROMPT") == picker.ARCHIVE_PROMPT
    show_archived = args.all or (args.fzf and in_archive_view)
    shown = visible_sessions(ctx.sessions, ctx.state, ctx.running, show_archived)
    if args.json:
        print(json.dumps([_as_json(s, ctx) for s in shown], indent=2))
        return 0
    now, home = time.time(), str(Path.home())
    for session in shown:
        print(format_row(session, ctx.state, ctx.running, now, home))
    return 0


def _as_json(session: Session, ctx: Context) -> dict:
    live = ctx.running.get(session.id)
    return {
        "id": session.id,
        "title": title_of(session, ctx.state),
        "cwd": session.cwd,
        "branch": session.branch,
        "updated": session.updated,
        "pinned": session.id in ctx.state.pinned,
        "archived": session.id in ctx.state.archived,
        "label": ctx.state.labels.get(session.id, ""),
        "running": asdict(live) if live else None,
    }


def cmd_preview(paths: Paths, args: argparse.Namespace) -> int:
    """Print the details pane for one session."""
    ctx = load_context(paths)
    print(preview(resolve(ctx, args.session), ctx.state, ctx.running, str(Path.home())))
    return 0


def cmd_flag(paths: Paths, args: argparse.Namespace) -> int:
    """Set, clear or (when ``args.value`` is None) flip the pin or archive flag."""
    ctx = load_context(paths)
    session = resolve(ctx, args.session)
    ids = ctx.state.pinned if args.flag == "pin" else ctx.state.archived
    on = (session.id not in ids) if args.value is None else args.value
    if on:
        ids.add(session.id)
    else:
        ids.discard(session.id)
    save_state(paths.state_file, ctx.state)
    word = "pinned" if args.flag == "pin" else "archived"
    print(f"{'' if on else 'un'}{word}: {title_of(session, ctx.state)}")
    return 0


def cmd_label(paths: Paths, args: argparse.Namespace) -> int:
    """Set, change or clear a session's label."""
    ctx = load_context(paths)
    session = resolve(ctx, args.session)
    text = args.text
    if text is None:
        current = ctx.state.labels.get(session.id, "")
        print(f"Session: {title_of(session, ctx.state)}")
        try:
            text = input(f"New label (empty clears{', current: ' + current if current else ''}): ")
        except EOFError:
            return 1
    text = " ".join(text.split())
    if text:
        ctx.state.labels[session.id] = text
    else:
        ctx.state.labels.pop(session.id, None)
    save_state(paths.state_file, ctx.state)
    print(f"label {'set to ' + repr(text) if text else 'cleared'}")
    return 0


def cmd_stop(paths: Paths, args: argparse.Namespace) -> int:
    """Stop the Claude process running a session; the conversation stays saved."""
    ctx = load_context(paths)
    session = resolve(ctx, args.session)
    live = ctx.running.get(session.id)
    if live is None:
        print(f"Not running: {title_of(session, ctx.state)}")
        return 0
    _guard_not_self(live)
    question = (
        f"Stop '{title_of(session, ctx.state)}'?\n"
        f"It uses {live.rss_mb} MB (pid {live.pid}). Claude exits in its tab; "
        "the conversation stays saved and can be opened again."
    )
    if not args.yes and not confirm(question, yes="Yes, stop it", no="No, keep running"):
        return 0
    stop_process(live.pid)
    print(f"Stopped pid {live.pid}, freed about {live.rss_mb} MB.")
    return 0


def session_files(claude_dir: Path, session: Session) -> list[Path]:
    """Return the transcript and every per-session folder Claude keeps for it."""
    transcript = Path(session.path)
    candidates = [
        transcript,
        transcript.with_suffix(""),
        claude_dir / "file-history" / session.id,
        claude_dir / "session-env" / session.id,
    ]
    return [path for path in candidates if path.exists()]


def cmd_delete(paths: Paths, args: argparse.Namespace) -> int:
    """Move a session's files to the macOS Trash and forget its pin, archive and label."""
    ctx = load_context(paths)
    session = resolve(ctx, args.session)
    title = title_of(session, ctx.state)
    live = ctx.running.get(session.id)
    if live:
        raise CliError(f"'{title}' is running (pid {live.pid}). Stop it first, then delete it.")
    trash = shutil.which("trash")
    if trash is None:
        raise CliError(
            "The 'trash' command was not found. It is built into macOS 15 and later; "
            "on older macOS install it with: brew install trash"
        )
    question = (
        f"Delete '{title}'?\n"
        f"Folder: {short_path(session.cwd, str(Path.home()))}\n"
        "Its files move to the macOS Trash, so it can be recovered from there."
    )
    if not args.yes and not confirm(question, yes="Yes, delete", no="No, keep it"):
        return 0
    files = session_files(paths.claude_dir, session)
    result = subprocess.run([trash, *map(str, files)], capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise CliError(f"Could not move files to the Trash: {result.stderr.strip()}")
    ctx.state.pinned.discard(session.id)
    ctx.state.archived.discard(session.id)
    ctx.state.labels.pop(session.id, None)
    save_state(paths.state_file, ctx.state)
    print(f"Moved to Trash: {title}")
    return 0


def open_session(ctx: Context, session: Session) -> int:
    """Replace this process with ``claude --resume`` in the session's folder."""
    _require_folder(session)
    claude = shutil.which("claude")
    if claude is None:
        raise CliError("The 'claude' command is not on PATH.")
    live = ctx.running.get(session.id)
    if live:
        _guard_not_self(live)
        question = (
            f"This session is already running in another terminal (pid {live.pid}). "
            "Two copies would write to the same conversation. Stop that one and open it here?"
        )
        if not confirm(question, yes="Yes, move it here", no="No"):
            return 0
        stop_process(live.pid)
    os.chdir(session.cwd)
    os.execv(claude, ["claude", "--resume", session.id])
    return 0


def _require_folder(session: Session) -> None:
    if not Path(session.cwd).is_dir():
        raise CliError(
            f"Folder {session.cwd} no longer exists, so this session cannot be resumed. "
            f"Restore the folder, or archive the session: cs archive {session.id[:8]}"
        )


def cmd_open(paths: Paths, args: argparse.Namespace) -> int:
    """Resume a session here, or in a new tab with ``--tab``."""
    ctx = load_context(paths)
    session = resolve(ctx, args.session)
    if args.tab:
        print(open_in_tab(ctx, session))
        return 0
    return open_session(ctx, session)


def open_in_tab(ctx: Context, session: Session) -> str:
    """Open a session in a new tab, or switch to the tab already running it.

    Returns:
        A one-line message describing what happened.

    """
    title = title_of(session, ctx.state)
    app = terminal.current_terminal()
    try:
        live = ctx.running.get(session.id)
        if live:
            if terminal.focus_tab(app, live.pid):
                return f"Switched to the tab running '{title}'"
            return f"'{title}' is already running in another tab (pid {live.pid})"
        _require_folder(session)
        where = terminal.open_in_new_tab(app, session.cwd, session.id)
    except terminal.TerminalError as err:
        raise CliError(str(err)) from err
    if where == "window":
        return (
            f"Opened '{title}' in a new window. For tabs, allow Terminal in System Settings > "
            "Privacy & Security > Accessibility"
        )
    return f"Opened '{title}' in a new tab"


def cmd_open_tab(paths: Paths, args: argparse.Namespace) -> int:
    """Picker hook: open in a new tab and print fzf actions that report the result."""
    me = _self_command()
    try:
        ctx = load_context(paths)
        message = open_in_tab(ctx, resolve(ctx, args.session))
    except (CliError, StateError) as err:
        message = f"✗ {err}"
    print(f"{picker.reload_action(me)}+{picker.status_action(message)}")
    return 0


def cmd_toolbar(_paths: Paths, args: argparse.Namespace) -> int:
    """Picker hook: print the fzf actions for a click on a toolbar word."""
    print(picker.toolbar_action(args.word, args.session, _self_command()))
    return 0


def _self_command() -> str:
    return f"{shlex.quote(sys.executable)} -m claude_sessions"


def _require_fzf() -> str:
    fzf = shutil.which("fzf")
    if fzf is None:
        raise CliError("fzf is not installed. Install it with: brew install fzf")
    output = subprocess.run(
        [fzf, "--version"], capture_output=True, text=True, check=False
    ).stdout.strip()
    version = picker.parse_fzf_version(output)
    if version is None or version < picker.MIN_FZF_VERSION:
        needed = ".".join(map(str, picker.MIN_FZF_VERSION))
        raise CliError(
            f"cs needs fzf {needed} or newer, found '{output or 'unknown'}'. "
            "Upgrade with: brew upgrade fzf"
        )
    return fzf


def cmd_pick(paths: Paths, _args: argparse.Namespace) -> int:
    """Show the interactive picker.

    In Terminal.app and Ghostty the picker stays open and sessions open in new tabs;
    elsewhere the chosen session resumes in this terminal.
    """
    fzf = _require_fzf()
    new_tab = terminal.current_terminal() in terminal.TAB_TERMINALS
    ctx = load_context(paths)
    now, home = time.time(), str(Path.home())
    rows = [
        format_row(s, ctx.state, ctx.running, now, home)
        for s in visible_sessions(ctx.sessions, ctx.state, ctx.running, show_archived=False)
    ]
    result = subprocess.run(
        picker.fzf_command(fzf, _self_command(), new_tab),
        input="\n".join(rows),
        stdout=subprocess.PIPE,
        text=True,
        check=False,
    )
    if new_tab or result.returncode != 0 or not result.stdout.strip():
        return 0
    chosen = result.stdout.split("\t", 1)[0]
    ctx = load_context(paths)
    return open_session(ctx, resolve(ctx, chosen))


def build_parser() -> argparse.ArgumentParser:
    """Define the ``cs`` command line."""
    parser = argparse.ArgumentParser(
        prog="cs", description="Pick and manage Claude Code sessions across all folders."
    )
    parser.set_defaults(func=cmd_pick)
    sub = parser.add_subparsers(title="commands", metavar="COMMAND")

    def command(name: str, func, help_text: str | None) -> argparse.ArgumentParser:
        if help_text:
            p = sub.add_parser(name, help=help_text, description=help_text)
        else:
            # Without help text, picker hooks stay out of the command list.
            p = sub.add_parser(name)
        p.set_defaults(func=func)
        return p

    p = command("list", cmd_list, "List sessions (pinned, then running, then recent).")
    p.add_argument("--all", action="store_true", help="include archived sessions")
    p.add_argument("--json", action="store_true", help="print JSON instead of rows")
    p.add_argument("--fzf", action="store_true", help=argparse.SUPPRESS)
    p = command("open", cmd_open, "Resume a session in its own folder.")
    p.add_argument("session", help="id, id prefix or name")
    p.add_argument("--tab", action="store_true", help="open in a new terminal tab")
    for name, func, help_text in (
        ("preview", cmd_preview, "Show details and recent messages of a session."),
        ("delete", cmd_delete, "Move a session to the macOS Trash (asks first)."),
        ("stop", cmd_stop, "Stop a running session to free memory; it stays resumable."),
    ):
        p = command(name, func, help_text)
        p.add_argument("session", help="id, id prefix or name")
        if name in ("delete", "stop"):
            p.add_argument("-y", "--yes", action="store_true", help="do not ask first")
    for name, flag, value, help_text in (
        ("pin", "pin", True, "Pin a session to the top of the list."),
        ("unpin", "pin", False, "Unpin a session."),
        ("archive", "archive", True, "Archive a session (hidden unless running)."),
        ("unarchive", "archive", False, "Bring an archived session back."),
    ):
        p = command(name, cmd_flag, help_text)
        p.set_defaults(flag=flag, value=value)
        p.add_argument("session", help="id, id prefix or name")
    p = command("toggle", cmd_flag, "Flip pin or archive on a session.")
    p.set_defaults(value=None)
    p.add_argument("flag", choices=["pin", "archive"])
    p.add_argument("session", help="id, id prefix or name")
    p = command("label", cmd_label, "Set a label; omit TEXT to be prompted, '' clears it.")
    p.add_argument("session", help="id, id prefix or name")
    p.add_argument("text", nargs="?", help="new label")
    p = command("open-tab", cmd_open_tab, None)
    p.add_argument("session")
    p = command("toolbar", cmd_toolbar, None)
    p.add_argument("word")
    p.add_argument("session")
    return parser


def main(argv: list[str] | None = None) -> int:
    """Entry point for the ``cs`` command."""
    args = build_parser().parse_args(argv)
    try:
        return args.func(Paths.from_env(), args)
    except (CliError, StateError) as err:
        if "FZF_PROMPT" in os.environ:
            # Launched from a picker key: plain stderr would vanish when fzf redraws.
            notice(str(err))
        else:
            print(f"cs: {err}", file=sys.stderr)
        return 1
