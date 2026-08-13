# git-agent — Commit and push procedure

> **Inline procedure.** Embedded verbatim into the follow-up message by the
> `/git-agent` menu ("Commit and push") via `pi.sendUserMessage` — it is not a
> skill and the menu delivers it inline. `{{PKG_DIR}}` is
> substituted with the package dir at send time.

Create an atomic conventional commit with `git-agent` and push it to the remote.

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
5. On auth error (401), retry with `--free`:
   ```bash
   git-agent commit --free --intent "<intent>"
   ```
6. Push to remote repository:
   ```bash
   git push
   ```
   (If upstream is not set, use `git push -u origin <branch>`).

CLI Reference: `{{PKG_DIR}}/references/cli.md`
