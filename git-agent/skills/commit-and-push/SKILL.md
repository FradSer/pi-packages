---
name: commit-and-push
description: Creates atomic conventional git commits using git-agent and pushes changes to the remote repository.
---

CRITICAL:
- Do NOT run `git status`, `git diff`, `git log`, or any other read commands before `git-agent commit`.
- Execute `git-agent commit` directly. `git-agent` (v0.7.0+) automatically detects active model attribution from session environment variables (`PI_MODEL`, etc.).

## Execution

1. Derive a concise one-sentence intent from the conversation or invocation args.
2. Pass `--co-author "<co-author>"` if explicitly specified in invocation args or user instructions.
3. Run primary commit command:
   ```bash
   git-agent commit --intent "<intent>"
   ```
4. On auth error (401), retry with `--free`:
   ```bash
   git-agent commit --free --intent "<intent>"
   ```
5. Push to remote repository:
   ```bash
   git push
   ```
   (If upstream is not set, use `git push -u origin <branch>`).

CLI Reference: `../../references/cli.md`
