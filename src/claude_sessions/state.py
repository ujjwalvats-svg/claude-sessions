"""User-owned picker state: pinned and archived sessions, and custom labels."""

import json
from dataclasses import dataclass, field
from pathlib import Path


class StateError(Exception):
    """The state file exists but cannot be used."""


@dataclass
class State:
    """Pins, archived sessions and labels, keyed by session id."""

    pinned: set[str] = field(default_factory=set)
    archived: set[str] = field(default_factory=set)
    labels: dict[str, str] = field(default_factory=dict)


def load_state(path: Path) -> State:
    """Read the state file, or return empty state if it does not exist yet.

    Raises:
        StateError: The file is not valid state JSON. It is left untouched so pins
            and labels are never silently lost.

    """
    try:
        data = json.loads(path.read_text())
    except FileNotFoundError:
        return State()
    except json.JSONDecodeError as err:
        raise StateError(f"{path} is not valid JSON ({err}). Fix or delete it.") from err
    if not isinstance(data, dict):
        raise StateError(f"{path} must contain a JSON object. Fix or delete it.")
    return State(
        pinned=set(data.get("pinned", [])),
        archived=set(data.get("archived", [])),
        labels=dict(data.get("labels", {})),
    )


def save_state(path: Path, state: State) -> None:
    """Write the state file atomically."""
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "pinned": sorted(state.pinned),
        "archived": sorted(state.archived),
        "labels": dict(sorted(state.labels.items())),
    }
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2) + "\n")
    tmp.replace(path)
