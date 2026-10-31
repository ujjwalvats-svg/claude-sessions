from pathlib import Path

import pytest

from claude_sessions.state import State, StateError, load_state, save_state


def test_missing_state_file_is_empty_state(tmp_path: Path) -> None:
    assert load_state(tmp_path / "nope.json") == State()


def test_state_round_trips(tmp_path: Path) -> None:
    path = tmp_path / "dir" / "state.json"
    state = State(pinned={"a"}, archived={"b", "c"}, labels={"a": "order sync"})

    save_state(path, state)

    assert load_state(path) == state


@pytest.mark.parametrize("content", ["{broken", "[1, 2]"])
def test_unusable_state_file_fails_and_is_left_alone(tmp_path: Path, content: str) -> None:
    path = tmp_path / "state.json"
    path.write_text(content)

    with pytest.raises(StateError, match="Fix or delete it"):
        load_state(path)
    assert path.read_text() == content
