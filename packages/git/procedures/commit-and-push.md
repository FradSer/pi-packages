# Git — Commit and push procedure (standard git)

> **Inline procedure.** Embedded verbatim into the follow-up message by the
> `/git` menu ("Commit and push") via `pi.sendUserMessage` — it is not a
> skill. `{{PKG_DIR}}` is substituted with the package dir at send time.

Create clean, atomic Conventional Commits using standard `git` commands and push them to origin.

## Workflow

1. **Inspect status and diff**:
   ```bash
   git status --porcelain
   git diff --staged
   git diff
   ```
2. **Stage files**:
   ```bash
   git add <file1> <file2> ...
   ```
3. **Commit**:
   Formulate a Conventional Commit message and commit:
   ```bash
   git commit -m "<type>(<scope>): <summary>"
   ```
4. **Push**:
   Detect current branch and push:
   ```bash
   BRANCH=$(git branch --show-current)
   git push origin "$BRANCH"
   ```
   If pushing a new branch for the first time, append `-u`:
   ```bash
   git push -u origin "$BRANCH"
   ```
