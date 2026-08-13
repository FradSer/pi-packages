# Utils Pi Package

A pi-native `/effort` command for setting the session thinking level, plus a
git worktree path redirect for keeping linked worktrees inside the repo.

## Installation

```bash
# published
pi install npm:@fradser/utils
# or from this repo: pi install /path/to/pi-packages/packages/utils
```

## Commands

### `effort` — set the thinking level

`/effort` with no argument opens a menu of the thinking levels the current
model supports (the current level is marked). With an argument it sets the
level directly:

```
/effort          # menu
/effort max      # set directly
/effort min      # aliases: min, med, xh, none, 0
```

Valid levels: `off`, `minimal`, `low`, `medium`, `high`, `xhigh`, `max`.
Unknown values are rejected with a hint listing the valid levels. The level
is clamped to the model's capabilities, and the menu is narrowed to what the
model actually supports (a reasoning-off model only gets `off`).

## Git worktree redirect

Any `git worktree add` bash command is transparently rewritten so the linked
worktree lives inside `.pi/worktrees/<name>` instead of a sibling directory:

```
git worktree add ../foo feature/foo
# → mkdir -p .pi/worktrees && git worktree add .pi/worktrees/foo feature/foo
```

Flags (`-b`, `-B`, `--reason`, `--lock`) and trailing positional arguments
(branch, start commit) are preserved, and a path that is already inside
`.pi/worktrees/` is left untouched.

## License

MIT
