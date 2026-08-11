---
name: commit
description: Creates atomic conventional git commits using git-agent. This skill should be used when the user requests "commit", "git commit", "create commit", or wants to commit changes using AI atomic commits.
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
4. If specific files are already staged, pass `--no-stage`:
   ```bash
   git-agent commit --no-stage --intent "<intent>"
   ```
5. On auth error (401), retry with `--free`:
   ```bash
   git-agent commit --free --intent "<intent>"
   ```
6. **Fallback** (if `git-agent` binary is not found): follow manual commit fallback ladder in `../../references/coauthor-attribution.md` using `GIT_SKILL_FALLBACK=1`.

CLI Reference: `../../references/cli.md`
