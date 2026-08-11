# Co-Author Attribution & Standard Commit Reference

Standard Git commit and co-author rules for GitFlow operations in the `git` package.

## 1. Conventional Commit Format

When committing version bumps, changelog updates, or branch changes, delegate to the `/commit` skill. Pass the desired Conventional Commit message as the intent:

- `chore: bump version to <TARGET>` — version bumps
- `docs: update changelog for <NAME>` — changelog updates
- `feat`, `fix`, `chore`, `docs` — branch changes per type

The `/commit` skill creates an atomic commit from the intent and stages only the files that belong to the change.

## 2. Co-Author Attribution

If a co-author trailer is requested by user prompt or environment configuration, pass it to the `/commit` skill so the trailer is appended to the commit message.