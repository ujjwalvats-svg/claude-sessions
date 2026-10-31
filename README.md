# claude-sessions (`cs`)

One list of every [Claude Code](https://claude.com/claude-code) session on your Mac, across
every folder. Pick one and it opens in the folder it belongs to. No more remembering session
ids or which directory a conversation started in.

```
╭──────────── Double-click or Enter: open in a new tab ─────────────╮
│ ctrl-p pin · ctrl-a archive · ctrl-t show archived · ctrl-e label │
│ ctrl-x stop · ctrl-d delete · esc quit                            │
╰───────────────────────────────────────────────────────────────────╯
 ★●  Order sync QA                ~/work/order-service   now  main   402MB busy
 ★   Inventory webhook retries    ~/work/inventory        2h  fix/retry
  ●  Chrome remote debug setup    ~                      11m         165MB idle
     Cart key collision           ~/work/storefront       1d  main
     Java interview prep          ~/notes                 3d
─────────────────────────────────────────────────────────────────────────────
  🗑 Delete     ■ Stop     ★ Pin     ⊘ Archive     ✎ Label
```

`★` pinned · `●` running (with memory use) · a preview pane on the right shows the
selected session's details and its last few messages.

> This is an independent community tool. It is not made or supported by Anthropic.

## Why

If you run Claude Code in the terminal you build up dozens or hundreds of sessions. You
only work in two or three at a time, but you want the others back later. Today that means:

- remembering session ids for `claude --resume <id>`, and
- remembering which folder each session was started in, because `claude --resume` only
  looks at the current folder.

Sessions you forget to exit keep running and keep using memory, often 150–400 MB each.

`cs` fixes all three: one searchable list, one click to open, and an easy way to see and
stop what is still running.

## Features

- **Every session in one list**, from every folder, with a readable name (your label,
  your `/rename` name, Claude's generated title, or the last prompt).
- **Opens in the right folder.** Double-click and the session resumes where it started.
- **New tab per session** in Terminal.app and Ghostty; the list stays open. Double-click a
  session that is already running and Terminal.app switches to its tab instead of starting
  a second copy.
- **See what is running** and how much memory it uses. The list refreshes every 3 seconds.
- **Stop** idle sessions to free memory. The conversation stays saved and can be reopened.
- **Pin** the sessions you are working on now; **archive** the ones you don't need.
- **Label** sessions with your own names.
- **Delete** sessions you will never need again. A confirmation box asks first, and the
  files go to the macOS Trash, so you can still restore them.
- **Search** by typing; **mouse** support for selecting, opening and the toolbar.
- **Scriptable**: every action is also a command, with JSON output for scripts and agents.
- Fast: a cached index makes the list open in about 50 ms, even with hundreds of sessions.

## Requirements

| What | Version | Notes |
|---|---|---|
| macOS | any recent | Tested on macOS. Listing, opening and stopping may work on Linux but are untested there |
| [Claude Code](https://claude.com/claude-code) | CLI | `claude` must be on your `PATH` |
| Python | 3.10 or newer | No third-party Python packages are needed |
| [fzf](https://github.com/junegunn/fzf) | 0.73.0 or newer | Draws the list; `cs` tells you if yours is too old |
| `trash` | | Only for delete. Built into macOS 15+; older macOS: `brew install trash` |
| Terminal.app or Ghostty | | Only for opening sessions in new tabs. Other terminals open sessions in the same window |

## Install

1. Install fzf:

   ```sh
   brew install fzf
   ```

2. Install `cs`, using whichever Python tool you already have:

   ```sh
   # uv (recommended)
   uv tool install git+https://github.com/ujjwalvats-svg/claude-sessions

   # or pipx
   pipx install git+https://github.com/ujjwalvats-svg/claude-sessions

   # or pip, from a clone
   git clone https://github.com/ujjwalvats-svg/claude-sessions
   cd claude-sessions
   pip install -r requirements.txt
   ```

3. Open a **new** terminal tab and run:

   ```sh
   cs
   ```

If your shell says `command not found: cs`, the install folder is not on your `PATH`.
Run `uv tool update-shell` (uv) or `pipx ensurepath` (pipx), then open a new tab.

## Using the picker

Run `cs`. Type to search, use the arrow keys or the mouse to move, and:

| Key | Toolbar | What it does |
|---|---|---|
| Enter / double-click | | Open the session |
| `ctrl-p` | ★ Pin | Pin or unpin. Pinned sessions stay at the top |
| `ctrl-a` | ⊘ Archive | Archive or unarchive. Archived sessions are hidden unless they are running |
| `ctrl-t` | | Show or hide archived sessions |
| `ctrl-e` | ✎ Label | Give the session your own name (leave empty to remove it) |
| `ctrl-x` | ■ Stop | Stop a running session to free its memory (asks first) |
| `ctrl-d` | 🗑 Delete | Move the session's files to the Trash (asks first) |
| `esc` | | Quit |

Toolbar buttons act on the highlighted row: click a row, then click the button.

**Order of the list:** pinned first, then running, then most recently used.

### Opening sessions in new tabs

In **Terminal.app** and **Ghostty**, opening a session starts it in a new tab and leaves
the list open, so you can open several sessions one after another. The result shows on
the list's top border, for example `Opened 'Order sync QA' in a new tab`.

In other terminals, opening a session closes the list and resumes the session in the same
window.

**Terminal.app permission.** Terminal.app has no scripting command for "new tab", so `cs`
presses ⌘T for you through System Events. The first time, macOS asks whether Terminal may
control System Events and use Accessibility. Allow both. If you said no, enable it later in
**System Settings → Privacy & Security → Accessibility → Terminal**. Without the permission
sessions open in a new window instead of a tab, and `cs` tells you so.

### Stopping and exiting

A session uses memory only while Claude is running in it. When you are done, type `/exit`
in Claude. The conversation is saved; pick it in `cs` later to continue. Use **■ Stop**
(`ctrl-x`) for sessions you left running in some other tab.

### Deleting

**🗑 Delete** (`ctrl-d`) shows a confirmation box with the session's name and folder.
**No, keep it** is selected by default. If you choose **Yes, delete**, the transcript and
the session's other folders go to the macOS Trash, and its pin, archive flag and label are
forgotten. Running sessions cannot be deleted; stop them first.

## Commands

Everything the picker does is also a command, so you can script it or let an agent use it.
`SESSION` can be a full session id, a unique start of one (`3f2a`), your label, or the name
you gave the session with `/rename`.

| Command | What it does |
|---|---|
| `cs` | Open the picker |
| `cs list [--all] [--json]` | Print the list. `--all` includes archived sessions |
| `cs open SESSION [--tab]` | Resume a session in its folder, here or in a new tab |
| `cs preview SESSION` | Show details and the last few messages |
| `cs pin SESSION` / `cs unpin SESSION` | Pin or unpin |
| `cs archive SESSION` / `cs unarchive SESSION` | Archive or unarchive |
| `cs label SESSION [TEXT]` | Set a label; without `TEXT` you are asked; `""` removes it |
| `cs stop SESSION [--yes]` | Stop a running session |
| `cs delete SESSION [--yes]` | Move a session to the Trash |

Examples:

```sh
cs list --json | jq '.[] | select(.running) | {title, mb: .running.rss_mb}'
cs label 3f2a "order sync QA"
cs open "order sync QA" --tab
cs stop 3f2a --yes
```

## How it works

`cs` reads the files Claude Code already keeps. It does not change them, except that delete
moves a session's files to the Trash.

| Path | Used for |
|---|---|
| `~/.claude/projects/*/<id>.jsonl` | One file per session: folder, git branch, titles, messages |
| `~/.claude/sessions/<pid>.json` | Written by each running Claude process; tells `cs` what is running |
| `~/.config/claude-sessions/state.json` | Your pins, archived sessions and labels (written by `cs`) |
| `~/.cache/claude-sessions/index.json` | Cached summary of each transcript. Safe to delete |

- Opening runs `claude --resume <id>` from the session's folder.
- Stopping sends the Claude process `SIGTERM`, the same signal a normal quit uses.
- Deleting moves these to the Trash: the transcript, `projects/<folder>/<id>/`,
  `file-history/<id>/` and `session-env/<id>/`.
- `CLAUDE_CONFIG_DIR`, `XDG_CONFIG_HOME` and `XDG_CACHE_HOME` are honored.
- Nothing is sent over the network.

## Troubleshooting

| Problem | Fix |
|---|---|
| `command not found: cs` | Open a new terminal tab. Still missing: `uv tool update-shell` or `pipx ensurepath` |
| `cs` runs a different program | Another tool (for example Coursier) also installs `cs`. Add `alias cs="$HOME/.local/bin/cs"` to `~/.zshrc`, or call it by its full path |
| `cs needs fzf 0.73.0 or newer` | `brew upgrade fzf` |
| Sessions open in a new window, not a tab | Give Terminal Accessibility permission (see above) |
| A session is missing from the list | It may be archived: press `ctrl-t`. Sessions that never got a first message have no folder and are not shown |
| `Folder ... no longer exists` | The project folder was moved or deleted. Put it back, or archive or delete the session |
| Stop says the process is still running | Claude did not quit within 5 seconds. Run the `kill -9 <pid>` it prints |
| Damaged state file error | Fix or delete `~/.config/claude-sessions/state.json` (you lose pins and labels) |

## Uninstall

```sh
uv tool uninstall claude-sessions      # or: pipx uninstall claude-sessions
trash ~/.config/claude-sessions ~/.cache/claude-sessions
```

Your Claude Code sessions are not touched.

## Contributing

Bug reports and pull requests are welcome. See [CONTRIBUTING.md](CONTRIBUTING.md) for the
development setup.

## License

[MIT](LICENSE)
