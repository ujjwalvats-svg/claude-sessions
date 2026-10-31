import json
import os
import signal
import subprocess
import time
from collections.abc import Iterator
from pathlib import Path

import pytest


def write_transcript(path: Path, entries: list[dict], tail: str = "") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    compact = (json.dumps(e, separators=(",", ":")) for e in entries)
    path.write_text("".join(line + "\n" for line in compact) + tail)
    return path


def user(text: str, cwd: str = "/work", branch: str = "main", **extra: object) -> dict:
    return {
        "type": "user",
        "cwd": cwd,
        "gitBranch": branch,
        "message": {"role": "user", "content": text},
        **extra,
    }


def assistant(text: str) -> dict:
    return {"type": "assistant", "message": {"content": [{"type": "text", "text": text}]}}


@pytest.fixture
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point the CLI at an isolated Claude dir, config dir and cache dir."""
    claude_dir = tmp_path / "claude"
    (claude_dir / "projects").mkdir(parents=True)
    (claude_dir / "sessions").mkdir()
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(claude_dir))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    return claude_dir


@pytest.fixture
def fake_claude(tmp_path: Path) -> Iterator[int]:
    """Pid of a detached long-running process whose executable name is ``claude``.

    It is not a child of the test process, like a real session started in another
    terminal, so it disappears as soon as it exits instead of lingering as a zombie.
    """
    link = tmp_path / "bin" / "claude"
    link.parent.mkdir()
    link.symlink_to("/bin/sleep")
    launcher = subprocess.run(
        ["sh", "-c", f"'{link}' 60 >/dev/null 2>&1 & echo $!"],
        capture_output=True,
        text=True,
        check=True,
    )
    pid = int(launcher.stdout)
    yield pid
    if is_alive(pid):
        os.kill(pid, signal.SIGKILL)


def register_running(claude_dir: Path, pid: int, session_id: str) -> None:
    pid_file = claude_dir / "sessions" / f"{pid}.json"
    pid_file.write_text(json.dumps({"pid": pid, "sessionId": session_id, "status": "idle"}))


def is_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


def wait_gone(pid: int, timeout: float = 5.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not is_alive(pid):
            return True
        time.sleep(0.05)
    return False
