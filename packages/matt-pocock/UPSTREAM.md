# Upstream synchronization

- Repository: `mattpocock/skills`
- Upstream commit: `6654f6b60cd9d5be8b54c6fafe44346dabeb3b76`
- Upstream baseline: `v1.2.3`
- Checked: 2026-08-27

## Harness architecture

Upstream distributes nested `SKILL.md` files. Pi recursively discovers any
such file under a declared skill root, which exposes generic names such as
`tdd`, `code-review`, and `research` alongside unrelated installed skills.

This package exposes one extension command, `/matt-pocock`. The extension
selects and injects plain Markdown procedures from `procedures/`; none are Pi
skills, and the package contains no `SKILL.md` file.

## Sync rules

1. Clone and compare upstream before changing files.
2. Copy selected workflows and supporting files into `procedures/`; never
   overwrite the extension harness wholesale.
3. Rename copied upstream `SKILL.md` files to their workflow name plus `.md`.
   Strip their frontmatter, and never ship a `SKILL.md` file.
4. Remove Claude-only frontmatter, tools, paths, and invocation syntax from
   copied content. Replace cross-procedure calls with relative links.
5. Preserve the local BDD/tdd split and Pi-specific interaction,
   collaboration, instruction-file, and git-agent guidance.
6. Re-run the harness feature, package tests, and package dry-run after sync.
