---
name: commit
description: Creates atomic conventional git commits using git-agent. This skill should be used when the user requests "commit", "git commit", "create commit", or wants to commit changes using AI atomic commits.
---

CRITICAL:
- Do NOT run `git status`, `git diff`, `git log`, or any other read commands before `git-agent commit`.
- Execute `git-agent commit` directly. `git-agent` (v0.7.0+) automatically detects active model attribution from session environment variables (`PI_MODEL`, etc.).

## Execution

1. **Extract session context first.** Call the `session_context` tool to pull the recent user requests and decisions from the current session. (If the tool is unavailable, reconstruct the context from the conversation instead.)
2. **Build a detailed intent from that context.** The intent is the PRIMARY DIRECTIVE for the commit message generator — the richer it is, the more accurate the message. Cover:
   - **What** the user asked for (their words, not paraphrased into a tagline)
   - **Why** the change exists (decisions, rationale, rejected alternatives)
   - **How** it was verified (tests run, commands executed, quality gates)
   Write 2–4 sentences. Do not compress to a single sentence.
3. Pass `--co-author "<co-author>"` if explicitly specified in invocation args or user instructions.
4. Run primary commit command:
   ```bash
   git-agent commit --intent "<intent>"
   ```
5. If specific files are already staged, pass `--no-stage`:
   ```bash
   git-agent commit --no-stage --intent "<intent>"
   ```
6. On auth error (401), retry with `--free`:
   ```bash
   git-agent commit --free --intent "<intent>"
   ```

CLI Reference: `../../references/cli.md`
