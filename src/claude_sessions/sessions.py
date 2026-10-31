"""Discover Claude Code sessions on disk and detect which ones are running."""

import json
import os
import re
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path

CACHE_VERSION = 1
# Native installs run as "claude"; npm installs run under "node".
CLAUDE_PROCESS_NAMES = frozenset({"claude", "node"})
_BRANCH = re.compile(rb'"gitBranch":"([^"]*)"')
_META_HEAD = 48
_META_MARKERS = {
    b'"type":"custom-title"': ("custom_title", "customTitle"),
    b'"type":"ai-title"': ("ai_title", "aiTitle"),
    b'"type":"last-prompt"': ("last_prompt", "lastPrompt"),
}


@dataclass(frozen=True)
class Session:
    """One saved conversation, summarised from its transcript file."""

    id: str
    path: str
    cwd: str
    branch: str
    custom_title: str
    ai_title: str
    last_prompt: str
    first_prompt: str
    updated: float


@dataclass(frozen=True)
class Running:
    """A live Claude Code process attached to a session."""

    pid: int
    status: str
    rss_mb: int


def _parse(line: bytes) -> dict:
    try:
        entry = json.loads(line)
    except json.JSONDecodeError:
        # The newest line may be half-written while Claude is running; treat it as absent.
        return {}
    return entry if isinstance(entry, dict) else {}


def _user_text(entry: dict) -> str:
    if entry.get("isMeta"):
        return ""
    message = entry.get("message")
    content = message.get("content") if isinstance(message, dict) else None
    if isinstance(content, str) and not content.startswith("<"):
        return content.strip()
    return ""


def _string(entry: dict, key: str) -> str:
    value = entry.get(key, "")
    return value if isinstance(value, str) else ""


def _scan_line(line: bytes, fields: dict[str, str]) -> None:
    head = line[:_META_HEAD]
    for marker, (field, key) in _META_MARKERS.items():
        if marker in head:
            fields[field] = _string(_parse(line), key) or fields[field]
            return
    if not fields["cwd"] and b'"cwd":"' in line:
        fields["cwd"] = _string(_parse(line), "cwd")
    if match := _BRANCH.search(line):
        fields["branch"] = match.group(1).decode(errors="replace")
    if not fields["first_prompt"] and b'"type":"user"' in line:
        fields["first_prompt"] = _user_text(_parse(line))


def read_session(path: Path, mtime: float) -> Session | None:
    """Summarise one transcript, or return None if it has no working directory.

    Metadata lines are matched on their leading bytes so large message lines are
    never JSON-parsed unless needed.
    """
    fields = dict.fromkeys(
        ("cwd", "branch", "custom_title", "ai_title", "last_prompt", "first_prompt"), ""
    )
    with path.open("rb") as f:
        for line in f:
            _scan_line(line, fields)
    if not fields["cwd"]:
        return None
    return Session(id=path.stem, path=str(path), updated=mtime, **fields)


def _read_cache(cache_file: Path) -> dict:
    try:
        data = json.loads(cache_file.read_text())
    except (OSError, json.JSONDecodeError):
        # The cache is derived data; a damaged one is rebuilt from the transcripts.
        return {}
    if data.get("version") != CACHE_VERSION:
        return {}
    return data.get("files", {})


def _write_cache(cache_file: Path, files: dict) -> None:
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    tmp = cache_file.with_suffix(".tmp")
    tmp.write_text(json.dumps({"version": CACHE_VERSION, "files": files}))
    tmp.replace(cache_file)


def load_sessions(projects_dir: Path, cache_file: Path) -> list[Session]:
    """Return every session under ``projects_dir``, re-reading only changed files."""
    cached = _read_cache(cache_file)
    files: dict[str, dict] = {}
    sessions: list[Session] = []
    for path in sorted(projects_dir.glob("*/*.jsonl")):
        stat = path.stat()
        entry = cached.get(str(path))
        if entry and entry["mtime"] == stat.st_mtime and entry["size"] == stat.st_size:
            data = entry["session"]
        else:
            session = read_session(path, stat.st_mtime)
            data = asdict(session) if session else None
        files[str(path)] = {"mtime": stat.st_mtime, "size": stat.st_size, "session": data}
        if data:
            sessions.append(Session(**data))
    _write_cache(cache_file, files)
    return sessions


def _live_claude_pids(pids: list[int]) -> dict[int, int]:
    """Map each pid that is still a Claude process to its resident memory in MB."""
    if not pids:
        return {}
    result = subprocess.run(
        ["ps", "-o", "pid=,rss=,comm=", "-p", ",".join(map(str, pids))],
        capture_output=True,
        text=True,
        check=False,
    )
    live: dict[int, int] = {}
    for row in result.stdout.splitlines():
        parts = row.split(None, 2)
        if len(parts) == 3 and Path(parts[2]).name in CLAUDE_PROCESS_NAMES:
            live[int(parts[0])] = int(parts[1]) // 1024
    return live


def running_sessions(sessions_dir: Path) -> dict[str, Running]:
    """Return running sessions keyed by session id, from Claude's per-process files."""
    candidates: dict[int, tuple[str, str]] = {}
    for pid_file in sessions_dir.glob("*.json"):
        try:
            data = json.loads(pid_file.read_text())
        except (OSError, json.JSONDecodeError):
            # Claude rewrites or deletes these files while running; skip a torn read.
            continue
        pid, session_id = data.get("pid"), data.get("sessionId")
        if isinstance(pid, int) and isinstance(session_id, str):
            candidates[pid] = (session_id, str(data.get("status", "")))
    live = _live_claude_pids(sorted(candidates))
    return {
        candidates[pid][0]: Running(pid=pid, status=candidates[pid][1], rss_mb=rss)
        for pid, rss in live.items()
    }


def ancestor_pids() -> set[int]:
    """Return the pids of this process and all its parents."""
    pids: set[int] = set()
    pid = os.getpid()
    while pid > 1 and pid not in pids:
        pids.add(pid)
        result = subprocess.run(
            ["ps", "-o", "ppid=", "-p", str(pid)], capture_output=True, text=True, check=False
        )
        parent = result.stdout.strip()
        if not parent.isdigit():
            break
        pid = int(parent)
    return pids
