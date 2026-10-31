"""Ordering, list rows and preview text for the session picker."""

import json
from datetime import datetime
from pathlib import Path

from claude_sessions.sessions import Running, Session
from claude_sessions.state import State

TITLE_WIDTH = 50
FOLDER_WIDTH = 30
BRANCH_WIDTH = 18
PREVIEW_TAIL_BYTES = 1_000_000
PREVIEW_MESSAGES = 6
PREVIEW_MESSAGE_CHARS = 400

_GREEN = "\033[32m"
_YELLOW = "\033[33m"
_DIM = "\033[2m"
_RESET = "\033[0m"


def title_of(session: Session, state: State) -> str:
    """Pick the most specific human-readable name for a session."""
    candidates = (
        state.labels.get(session.id, ""),
        session.custom_title,
        session.ai_title,
        session.last_prompt,
        session.first_prompt,
    )
    for text in candidates:
        if text.strip():
            return " ".join(text.split())
    return "(no prompt)"


def visible_sessions(
    sessions: list[Session], state: State, running: dict[str, Running], show_archived: bool
) -> list[Session]:
    """Order sessions pinned first, then running, then most recently used.

    Archived sessions are left out unless ``show_archived`` is set or they are running,
    since a running session still uses memory.
    """
    shown = [s for s in sessions if show_archived or s.id not in state.archived or s.id in running]
    return sorted(shown, key=lambda s: (s.id not in state.pinned, s.id not in running, -s.updated))


def fit(text: str, width: int, keep_end: bool = False) -> str:
    """Pad or truncate ``text`` to exactly ``width`` characters."""
    if len(text) <= width:
        return text.ljust(width)
    if keep_end:
        return "…" + text[-(width - 1) :]
    return text[: width - 1] + "…"


def age(updated: float, now: float) -> str:
    """Render the time since ``updated`` compactly, e.g. ``5m``, ``3h``, ``2d``."""
    seconds = max(0, int(now - updated))
    for unit, size in (("mo", 30 * 86400), ("d", 86400), ("h", 3600), ("m", 60)):
        if seconds >= size:
            return f"{seconds // size}{unit}"
    return "now"


def short_path(path: str, home: str) -> str:
    """Replace the home directory prefix with ``~``."""
    if path == home or path.startswith(home + "/"):
        return "~" + path[len(home) :]
    return path


def format_row(
    session: Session, state: State, running: dict[str, Running], now: float, home: str
) -> str:
    """Build one tab-separated picker row; the first field is the session id."""
    live = running.get(session.id)
    pin = f"{_YELLOW}★{_RESET}" if session.id in state.pinned else " "
    dot = f"{_GREEN}●{_RESET}" if live else " "
    title = fit(title_of(session, state), TITLE_WIDTH)
    if session.id in state.archived:
        title = f"{_DIM}{title}{_RESET}"
    folder = fit(short_path(session.cwd, home), FOLDER_WIDTH, keep_end=True)
    branch = fit("" if session.branch == "HEAD" else session.branch, BRANCH_WIDTH)
    memory = f"{_GREEN}{live.rss_mb}MB {live.status}{_RESET}" if live else ""
    columns = [pin + dot, title, folder, age(session.updated, now).rjust(4), branch, memory]
    return session.id + "\t" + "  ".join(columns)


def _message_text(entry: dict) -> tuple[str, str] | None:
    role = entry.get("type")
    if role not in ("user", "assistant") or entry.get("isMeta"):
        return None
    message = entry.get("message")
    content = message.get("content") if isinstance(message, dict) else None
    if isinstance(content, str):
        text = content
    elif isinstance(content, list):
        text = "\n".join(
            block.get("text", "")
            for block in content
            if isinstance(block, dict) and block.get("type") == "text"
        )
    else:
        return None
    text = text.strip()
    if not text or text.startswith("<"):
        return None
    return role, text


def recent_messages(path: Path, limit: int = PREVIEW_MESSAGES) -> list[tuple[str, str]]:
    """Return the last ``limit`` user/assistant text messages from a transcript."""
    with path.open("rb") as f:
        size = f.seek(0, 2)
        f.seek(max(0, size - PREVIEW_TAIL_BYTES))
        lines = f.read().splitlines()
    if size > PREVIEW_TAIL_BYTES:
        lines = lines[1:]
    messages: list[tuple[str, str]] = []
    for line in reversed(lines):
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        message = _message_text(entry) if isinstance(entry, dict) else None
        if message:
            messages.append(message)
            if len(messages) == limit:
                break
    return messages[::-1]


def preview(session: Session, state: State, running: dict[str, Running], home: str) -> str:
    """Render the details pane shown next to the picker list."""
    live = running.get(session.id)
    status = f"running (pid {live.pid}, {live.rss_mb} MB, {live.status})" if live else "stopped"
    flags = [
        name
        for name, ids in (("pinned", state.pinned), ("archived", state.archived))
        if session.id in ids
    ]
    updated = datetime.fromtimestamp(session.updated).strftime("%Y-%m-%d %H:%M")
    lines = [
        title_of(session, state),
        "",
        f"id:      {session.id}",
        f"folder:  {short_path(session.cwd, home)}",
        f"branch:  {session.branch or '-'}",
        f"updated: {updated}",
        f"status:  {status}",
    ]
    if flags:
        lines.append(f"flags:   {', '.join(flags)}")
    if not Path(session.cwd).is_dir():
        lines.append("warning: folder no longer exists; this session cannot be resumed")
    lines += ["", "── recent messages ──"]
    for role, text in recent_messages(Path(session.path)):
        shown = text if len(text) <= PREVIEW_MESSAGE_CHARS else text[:PREVIEW_MESSAGE_CHARS] + "…"
        lines += ["", f"[{role}]", shown]
    return "\n".join(lines)
