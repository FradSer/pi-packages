# Upstream synchronization

## Recorded revisions

- Repository: `mattpocock/skills`
- Compared commit: `6654f6b60cd9d5be8b54c6fafe44346dabeb3b76`
- Comparison tag: `v1.2.3`
- Resolved tag commit: `6acc160e4e0cd062dbbbd7a1b26ae92855edf07e`
- Latest checked commit: `3cca18b368ae95cdbdebbff572ccafa662551015`

These values are deliberately separate. The compared commit is the content
baseline, the comparison tag is the human-readable release marker, the resolved
tag commit records what that tag pointed to, and the latest checked commit is
the newest upstream tree reviewed for additions or removals.

The machine-readable selection is in
[`upstream-selection.json`](upstream-selection.json). It classifies every
upstream `SKILL.md` present at the latest checked commit as either promoted or
intentionally excluded. Each promoted skill names its local catalog capability,
plain Markdown resource, and upstream invocation mode. Each exclusion carries a
reason; Claude Code hooks and background-agent commands are identified as
host-specific rather than silently ignored.

## Harness architecture

Upstream distributes nested `SKILL.md` files. Pi recursively discovers any
such file under a declared skill root, which exposes generic names such as
`tdd`, `code-review`, and `research` alongside unrelated installed skills.

This package exposes one extension command, `/matt-pocock`. The extension
selects and injects plain Markdown procedures from `procedures/`; none are Pi
skills, and the package contains no `SKILL.md` file.

## Sync rules

1. Clone upstream separately and inspect both the compared and latest checked
   commits before changing local resources.
2. Run the local metadata check without an upstream checkout:

   ```bash
   node scripts/check-upstream-sync.mjs
   ```

3. Run the complete inventory, invocation, and content comparison against an
   already-cloned checkout. The checker never clones or fetches:

   ```bash
   node scripts/check-upstream-sync.mjs --upstream /path/to/mattpocock-skills
   ```

4. Copy selected workflows and supporting files into `procedures/`; never
   overwrite the extension harness wholesale.
5. Rename copied upstream `SKILL.md` files to their catalog id plus `.md`.
   Strip frontmatter, and never ship a `SKILL.md` file.
6. Remove Claude-only frontmatter, tools, paths, and invocation syntax from
   copied content. Replace cross-procedure calls with relative links.
7. Preserve the local BDD/TDD split and Pi-specific interaction,
   collaboration, instruction-file, and git-agent guidance. An adapted content
   result is expected when these local contracts differ from upstream.
8. Classify every new or removed upstream skill in
   `upstream-selection.json`, then update the four revision fields together.
9. Re-run the harness feature, isolated sync tests, package tests, and package
   dry-run after a sync.
