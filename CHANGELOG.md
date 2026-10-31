# Changelog

All notable changes to this project are listed here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/).

## [Unreleased]

## [0.1.0] - 2026-10-31

### Added

- `cs` picker listing every Claude Code session across all folders, with readable names,
  folder, last-used time, git branch, running state and memory use.
- Opening a session resumes it in its own folder: in a new tab in Terminal.app and
  Ghostty (switching to the existing tab when it is already running in Terminal.app), or in
  the same window elsewhere.
- Pin, archive, label, stop and delete, from keys, a clickable toolbar and commands.
- Confirmation boxes for stop and delete; delete moves files to the macOS Trash.
- Preview pane with session details and recent messages.
- Automatic list refresh every 3 seconds.
- `cs list --json` for scripts and agents.
- Cached transcript index so the list opens quickly with hundreds of sessions.
- Clear errors for a missing or too-old fzf, deleted project folders and a damaged state
  file.

[Unreleased]: https://github.com/ujjwalvats-svg/claude-sessions/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/ujjwalvats-svg/claude-sessions/releases/tag/v0.1.0
