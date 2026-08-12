# Git Agent Package for Pi

AI-first Git CLI automation — atomic AI commits, co-change relations (`git-agent related`), pre-tool hook safety, and workspace initialization.

## Overview

This package integrates `git-agent` into the Pi coding agent environment:

- **Atomic Commits**: Automatically splits staged changes into up to 5 logically distinct commits with AI-generated conventional messages (`git-agent commit`).
- **Co-change Relations**: Mined from git commit history to reveal files and test suites that historically change together (`git-agent related`).
- **Automatic Model Identity Resolution**: `git-agent` auto-detects active agent environment variables (`PI_MODEL`, `CLAUDE_CODE_MODEL`, `CODEX_MODEL`, `MODEL`), eliminating the need to pass manual co-author flags.
- **Native Extension Guard**: A pi extension (`extensions/validate-commit.ts`) intercepts raw `git commit` / `git add` tool calls and redirects to `git-agent` atomic commits.

## Skills Included

- `commit`: Creates atomic conventional commits via `git-agent`.
- `commit-and-push`: Creates atomic conventional commits and pushes to the remote repository.
- `related`: Mines git history for historically coupled files and test suites (`git-agent related`).
- `init`: Regenerates commit scopes and `.gitignore` rules from history (`git-agent init`).

## Installation

```bash
# published
pi install npm:@fradser/git-agent
# or from this repo: pi install /path/to/pi-packages/packages/git-agent
```

## License

MIT
