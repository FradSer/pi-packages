# Git — Commit procedure (standard git)

> **Inline procedure.** Embedded verbatim into the follow-up message by the
> `/git` menu ("Commit changes") via `pi.sendUserMessage` — it is not a skill.
> `{{PKG_DIR}}` is substituted with the package dir at send time.

Create clean, atomic Conventional Commits using standard `git` commands.

## Workflow

1. **Inspect status and diff**:
   ```bash
   git status --porcelain
   git diff --staged
   git diff
   ```
2. **Stage files**:
   Stage relevant modified or untracked files explicitly:
   ```bash
   git add <file1> <file2> ...
   ```
3. **Formulate Conventional Commit Message**:
   Follow the specification: `<type>(<optional scope>): <short description>`
   Types: `feat`, `fix`, `docs`, `style`, `refactor`, `perf`, `test`, `build`, `ci`, `chore`.
4. **Commit**:
   Execute standard `git commit`:
   ```bash
   git commit -m "<type>(<scope>): <summary>"
   ```
   If a co-author trailer is required or requested, follow `{{PKG_DIR}}/references/coauthor-attribution.md`.
