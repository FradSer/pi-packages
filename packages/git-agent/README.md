# Git Agent Package for Pi

AI-first Git CLI automation — atomic AI commits, co-change relations (`git-agent related`), pre-tool hook safety, and workspace initialization. Native `/git-agent` command menu — **no skill surface**.

## Overview

This package integrates `git-agent` into the Pi coding agent environment:

- **Atomic Commits**: Automatically splits staged changes into up to 5 logically distinct commits with AI-generated conventional messages (`git-agent commit`).
- **Co-change Relations**: Mined from git commit history to reveal files and test suites that historically change together (`git-agent related`).
- **Automatic Model Identity Resolution**: `git-agent` auto-detects active agent environment variables (`PI_MODEL`, `CLAUDE_CODE_MODEL`, `CODEX_MODEL`, `MODEL`), eliminating the need to pass manual co-author flags.
- **Native Extension Guard**: A pi extension (`extensions/validate-commit.ts`) intercepts raw `git commit` / `git add` tool calls and redirects to `git-agent` atomic commits.
- **Session-Grounded Commits**: A pi extension (`extensions/session-context.ts`) exposes the `session_context` tool, which reads the live session entries so commit intents are built from what the user actually asked for (requests, decisions, verification), not a compressed one-liner.

## Usage

Type `/git-agent` to open the native menu:

```
git-agent workflows:
❯ 1. Commit changes        (procedures/commit.md)
  2. Commit and push       (procedures/commit-and-push.md)
  3. Init / optimize       (procedures/init.md)
  4. Related files & tests (procedures/related.md)
```

Shorthand — pass a workflow keyword on the command line to skip the menu:

```bash
/git-agent commit                # commit with intent built from session context
/git-agent commit --co-author "Alice <a@example.com>"
/git-agent related src/foo.ts    # co-change for specific files
/git-agent related --tests src/
/git-agent init                  # regenerate scopes + .gitignore
```

Each selection embeds the full procedure (`procedures/*.md`) into a follow-up
message via `pi.sendUserMessage` — no skill docs, no path lookups. A short
guidance block is injected into the system prompt so natural-language requests
("commit this", "commit and push") route straight to the procedures.

## Installation

```bash
# published
pi install npm:@fradser/git-agent
# or from this repo: pi install /path/to/pi-packages/packages/git-agent
```

## Files

```
git-agent/
├── extensions/
│   ├── menu.ts               # /git-agent command menu + guidance injection
│   ├── session-context.ts    # session_context tool (intent source for commits)
│   └── validate-commit.ts    # blocks raw git add/commit, redirects to git-agent
├── procedures/
│   ├── commit.md             # atomic AI commit workflow
│   ├── commit-and-push.md    # commit + push workflow
│   ├── init.md               # scope/.gitignore regeneration
│   └── related.md            # co-change queries
└── references/
    ├── cli.md                # git-agent CLI reference
    └── coauthor-attribution.md
```

## License

MIT
