"""Yes/no questions and notices: a clickable fzf dialog on a terminal, plain text otherwise."""

import shutil
import subprocess
import sys
import textwrap

DIALOG_WIDTH = 56


def _interactive() -> bool:
    return sys.stdin.isatty() and sys.stdout.isatty()


def _fzf_dialog(fzf: str, message: str, choices: list[str], label: str) -> str:
    lines = [
        wrapped
        for paragraph in message.splitlines()
        for wrapped in (textwrap.wrap(paragraph, DIALOG_WIDTH) or [""])
    ]
    result = subprocess.run(
        [
            fzf,
            "--no-input",
            "--no-info",
            "--layout=reverse",
            "--border=rounded",
            f"--border-label= {label} ",
            "--margin=20%,15%",
            "--padding=1,3",
            "--pointer=▶",
            f"--header={chr(10).join(lines)}",
            "--header-first",
        ],
        input="\n".join(choices),
        stdout=subprocess.PIPE,
        text=True,
        check=False,
    )
    return result.stdout.strip()


def confirm(message: str, yes: str = "Yes", no: str = "No") -> bool:
    """Ask a yes/no question; the safe answer comes first and is the default."""
    fzf = shutil.which("fzf")
    if fzf and _interactive():
        return _fzf_dialog(fzf, message, [no, yes], "Confirm") == yes
    try:
        answer = input(f"{message} [y/N] ")
    except EOFError:
        return False
    return answer.strip().lower() in ("y", "yes")


def notice(message: str) -> None:
    """Show a message the user must acknowledge, so it is not lost when a screen redraws."""
    fzf = shutil.which("fzf")
    if fzf and _interactive():
        _fzf_dialog(fzf, message, ["OK"], "Notice")
    else:
        print(message, file=sys.stderr)
