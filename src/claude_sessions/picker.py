"""fzf configuration for the session picker: key bindings, toolbar and status line."""

# The every(N) refresh event arrived in fzf 0.73.0, the newest feature the picker uses.
MIN_FZF_VERSION = (0, 73, 0)
MAIN_PROMPT = "sessions> "
ARCHIVE_PROMPT = "all> "
REFRESH_SECONDS = 3
OPEN_HINT = "Double-click or Enter: open in a new tab"
OPEN_HERE_HINT = "Double-click or Enter: open here"
TOOLBAR = "  🗑 Delete     ■ Stop     ★ Pin     ⊘ Archive     ✎ Label  "
KEYS = (
    "ctrl-p pin · ctrl-a archive · ctrl-t show archived · ctrl-e label\n"
    "ctrl-x stop · ctrl-d delete · esc quit"
)

_TOOLBAR_WORDS = {
    "🗑": "delete",
    "delete": "delete",
    "■": "stop",
    "stop": "stop",
    "★": "pin",
    "pin": "pin",
    "⊘": "archive",
    "archive": "archive",
    "✎": "label",
    "label": "label",
}


def parse_fzf_version(output: str) -> tuple[int, ...] | None:
    """Parse ``fzf --version`` output such as ``0.74.5 (Homebrew)``."""
    words = output.split()
    parts = words[0].split(".") if words else []
    if not parts or not all(part.isdigit() for part in parts):
        return None
    return tuple(int(part) for part in parts)


def status_action(message: str) -> str:
    """Return the fzf action that shows ``message`` on the header border."""
    return f"change-header-label: {' '.join(message.split())} "


def reload_action(me: str) -> str:
    """Return the fzf action that reloads the list, keeping the current archived view."""
    return f"reload({me} list --fzf)"


def toolbar_action(word: str, session_id: str, me: str) -> str:
    """Translate a click on a toolbar word into fzf actions for the selected session."""
    action = _TOOLBAR_WORDS.get(word.strip().lower())
    if not action or not session_id:
        return ""
    if action in ("pin", "archive"):
        return f"execute-silent({me} toggle {action} {session_id})+{reload_action(me)}"
    return f"execute({me} {action} {session_id})+{reload_action(me)}"


def fzf_command(fzf: str, me: str, new_tab: bool) -> list[str]:
    """Build the fzf invocation; ``me`` is the shell command that runs this tool.

    With ``new_tab`` the picker stays open and Enter opens sessions in new tabs; otherwise
    Enter exits the picker and the caller resumes the session in this terminal.
    """
    reload = reload_action(me)
    show_all = (
        f'transform:[ "$FZF_PROMPT" = "{ARCHIVE_PROMPT}" ] '
        f'&& echo "change-prompt({MAIN_PROMPT})+reload({me} list)" '
        f'|| echo "change-prompt({ARCHIVE_PROMPT})+reload({me} list --all)"'
    )
    binds = [
        f"ctrl-p:execute-silent({me} toggle pin {{1}})+{reload}",
        f"ctrl-a:execute-silent({me} toggle archive {{1}})+{reload}",
        f"ctrl-e:execute({me} label {{1}})+{reload}",
        f"ctrl-x:execute({me} stop {{1}})+{reload}",
        f"ctrl-d:execute({me} delete {{1}})+{reload}",
        f"ctrl-t:{show_all}",
        f'click-footer:transform:{me} toolbar "$FZF_CLICK_FOOTER_WORD" {{1}}',
        f"every({REFRESH_SECONDS}):{reload}",
    ]
    if new_tab:
        binds += [f"{key}:transform:{me} open-tab {{1}}" for key in ("enter", "double-click")]
    return [
        fzf,
        "--ansi",
        "--no-sort",
        "--track",
        "--id-nth=1",
        "--layout=reverse",
        "--delimiter=\t",
        "--with-nth=2..",
        f"--prompt={MAIN_PROMPT}",
        f"--header={KEYS}",
        "--header-border=rounded",
        f"--header-label= {OPEN_HINT if new_tab else OPEN_HERE_HINT} ",
        f"--footer={TOOLBAR}",
        "--footer-border=line",
        f"--preview={me} preview {{1}}",
        "--preview-window=right,45%,wrap",
        *(f"--bind={bind}" for bind in binds),
    ]
