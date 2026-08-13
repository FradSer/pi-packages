# Co-Author Attribution & Standard Commit Reference

Standard Git commit and co-author rules for GitFlow operations in the `git` package.

## 1. Conventional Commit Format

When committing version bumps, changelog updates, or branch changes, create a Conventional Commit with the desired message as the summary:

- `chore: bump version to <TARGET>` — version bumps
- `docs: update changelog for <NAME>` — changelog updates
- `feat`, `fix`, `chore`, `docs` — branch changes per type

The commit procedure stages only the files that belong to the change and commits them atomically.

## 2. Co-Author Attribution

If a co-author trailer is requested by user prompt or environment configuration, append it to the commit message.