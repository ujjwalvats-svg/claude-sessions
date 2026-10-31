# Contributing

Thanks for helping. Bug reports, ideas and pull requests are all welcome.

## Reporting a bug

Open an issue with:

- what you did and what you expected,
- what happened instead (error text or a screenshot),
- your macOS version, terminal app, `fzf --version`, `python3 --version` and
  `claude --version`.

## Development setup

You need [uv](https://docs.astral.sh/uv/), [fzf](https://github.com/junegunn/fzf) 0.73+ and
macOS.

```sh
git clone https://github.com/ujjwalvats-svg/claude-sessions
cd claude-sessions
uv sync                 # creates .venv with the dev tools
uv run cs               # run your working copy
prek install            # optional: run the checks before every commit
```

Without uv: `pip install -e . --group dev` (needs pip 25.1 or newer).

To use your working copy as your everyday `cs`:

```sh
uv tool install --editable .
```

## Checks

Run all four before opening a pull request. CI runs the same ones on Python 3.10 and 3.13.

```sh
uv run ruff format .
uv run ruff check .
uv run ty check .
uv run pytest -q
```

Code rules the checks enforce: 100-character lines, functions no more complex than
cyclomatic complexity 8, docstrings on public functions, and absolute imports only.

## Project layout

| File | Responsibility |
|---|---|
| `src/claude_sessions/sessions.py` | Reads transcripts (with a cache) and finds running Claude processes |
| `src/claude_sessions/state.py` | Pins, archive flags and labels in `state.json` |
| `src/claude_sessions/view.py` | List order, row text and the preview pane |
| `src/claude_sessions/picker.py` | fzf options: keys, toolbar, status line |
| `src/claude_sessions/dialog.py` | Yes/no confirmation boxes |
| `src/claude_sessions/terminal.py` | AppleScript for new tabs in Terminal.app and Ghostty |
| `src/claude_sessions/cli.py` | Commands, argument parsing and the picker loop |

The picker is fzf, and fzf's key bindings call `cs` subcommands. That means every picker
action is also a command anyone can run, so keep it that way when adding features.

## Tests

- Test behavior through the public commands where you can (`main([...])` in
  `tests/test_cli.py`).
- Tests never touch your real Claude data. The `env` fixture points `CLAUDE_CONFIG_DIR`,
  `XDG_CONFIG_HOME` and `XDG_CACHE_HOME` at a temp folder.
- Only the edges are faked: a `claude` process (a symlink to `sleep`), the macOS `trash`
  command, and AppleScript calls that would open real tabs. Everything else runs for real,
  including fzf and `osacompile`.
- Before a pull request, break the code you changed and check that a test fails.

## Pull requests

- One change per pull request, with a short description of what it does.
- Add a line to `CHANGELOG.md` under **Unreleased**.
- Update `README.md` if behavior or commands change.
