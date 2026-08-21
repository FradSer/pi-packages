# Repository Guidelines

## Project Structure

`packages/mattpocock/` publishes `pi-mattpocock`, a skills-only Pi package.
The manifest registers `skills/engineering` and `skills/productivity`; these
trees contain 27 `SKILL.md` files plus supporting references and scripts.
Package documentation is in `README.md`, upstream provenance and sync rules
are in `UPSTREAM.md`, and the BDD contract and executable checks are in
`features/migrate-mattpocock.feature` and `tests/test_package.py`.

## Commands

Run focused checks with:

```bash
python3 -m pytest packages/mattpocock/tests/ -q
npx tsc --noEmit -p tsconfig.extensions.json
pnpm --dir packages/mattpocock pack --dry-run
```

This package has no extension build; Pi consumes the declared skill trees.

## Style and Architecture

Keep skill frontmatter limited to the native `name` and `description` fields
(and documented optional Pi fields). Cross-skill links use `/skill:<name>`.
Do not introduce plugin manifests, `openai.yaml`, Claude-only frontmatter,
plugin-root environment variables, unsupported session tools, or bare command
names. Preserve relative links to each skill's references, templates, and
scripts. Upstream synchronization is selective: preserve the local BDD/tdd
split and Pi-specific interaction, collaboration, instruction-file, and
git-agent guidance; do not overwrite the adapted tree wholesale.

## Testing and Release

Update `features/migrate-mattpocock.feature` before changing package behavior,
then extend the Python contracts. Verify all 27 skills, native Pi manifest
metadata, supporting files, Pi invocations, and absence of Claude artifacts.
The package README currently directs users to local installation because its
first npm release is not available; keep that claim accurate. Its published
files are `skills`, `LICENSE`, and `README.md`. Add a Changeset for published
package changes and follow the repository's Conventional Commit scopes.
