import shutil
import subprocess

import pytest

from claude_sessions.picker import (
    fzf_command,
    parse_fzf_version,
    status_action,
    toolbar_action,
)


def binds(args: list[str]) -> dict[str, str]:
    pairs = (a.removeprefix("--bind=").split(":", 1) for a in args if a.startswith("--bind="))
    return dict(pairs)


def test_keys_act_on_the_selected_id() -> None:
    bound = binds(fzf_command("/bin/fzf", "cs", new_tab=True))
    assert "toggle pin {1}" in bound["ctrl-p"]
    assert "toggle archive {1}" in bound["ctrl-a"]
    assert "label {1}" in bound["ctrl-e"]
    assert "stop {1}" in bound["ctrl-x"]
    assert "delete {1}" in bound["ctrl-d"]
    assert "every(3)" in bound


def test_new_tab_mode_keeps_picker_open_on_enter_and_double_click() -> None:
    bound = binds(fzf_command("/bin/fzf", "cs", new_tab=True))
    assert bound["enter"] == "transform:cs open-tab {1}"
    assert bound["double-click"] == "transform:cs open-tab {1}"


def test_same_terminal_mode_leaves_enter_to_accept() -> None:
    bound = binds(fzf_command("/bin/fzf", "cs", new_tab=False))
    assert "enter" not in bound
    assert "double-click" not in bound


@pytest.mark.parametrize(
    ("word", "expected"),
    [
        ("🗑", "execute(cs delete abc)"),
        ("Delete", "execute(cs delete abc)"),
        ("■", "execute(cs stop abc)"),
        ("✎", "execute(cs label abc)"),
        ("Pin", "execute-silent(cs toggle pin abc)"),
        ("⊘", "execute-silent(cs toggle archive abc)"),
    ],
)
def test_toolbar_words_map_to_actions(word: str, expected: str) -> None:
    action = toolbar_action(word, "abc", "cs")
    assert action.startswith(expected + "+reload(")


@pytest.mark.parametrize(("word", "session_id"), [("", "abc"), ("nonsense", "abc"), ("Pin", "")])
def test_toolbar_ignores_blank_clicks_and_empty_lists(word: str, session_id: str) -> None:
    assert toolbar_action(word, session_id, "cs") == ""


def test_status_is_a_single_line_label() -> None:
    assert status_action("Opened\n'x'  now") == "change-header-label: Opened 'x' now "


@pytest.mark.skipif(shutil.which("fzf") is None, reason="fzf not installed")
@pytest.mark.parametrize("new_tab", [True, False])
def test_real_fzf_accepts_the_picker_options(new_tab: bool) -> None:
    fzf = shutil.which("fzf")
    assert fzf is not None
    result = subprocess.run(
        [*fzf_command(fzf, "cs", new_tab), "--filter=order"],
        input="id1\tOrder sync\nid2\tother",
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.stderr == ""
    assert result.stdout == "id1\tOrder sync\n"


@pytest.mark.skipif(shutil.which("fzf") is None, reason="fzf not installed")
@pytest.mark.parametrize("word", ["🗑", "Pin"])
def test_real_fzf_accepts_toolbar_actions(word: str) -> None:
    fzf = shutil.which("fzf")
    assert fzf is not None
    action = toolbar_action(word, "abc", "cs")
    result = subprocess.run(
        [fzf, "--filter=x", f"--bind=start:{action}"],
        input="x",
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.stderr == ""


@pytest.mark.parametrize(
    ("output", "expected"),
    [
        ("0.74.5 (Homebrew)", (0, 74, 5)),
        ("0.73.0", (0, 73, 0)),
        ("1.0 (devel)", (1, 0)),
        ("", None),
        ("fzf version unknown", None),
    ],
)
def test_parse_fzf_version(output: str, expected: tuple[int, ...] | None) -> None:
    assert parse_fzf_version(output) == expected
