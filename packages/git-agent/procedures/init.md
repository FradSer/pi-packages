# git-agent — Init / optimize procedure

> **Inline procedure.** Embedded verbatim into the follow-up message by the
> `/git-agent` menu ("Init / optimize") via `pi.sendUserMessage` — it is not a
> skill and the menu delivers it inline. `{{PKG_DIR}}` is substituted
> with the package dir at send time.

Initialize or optimize git-agent configuration, regenerate commit scopes from
git history, and re-derive `.gitignore` rules.

## Execution

Execute initialization or optimization based on invocation args:

1. **Optimize commit scopes** (regenerate from history):
   ```bash
   git-agent init --scope --force
   ```
2. **Re-derive `.gitignore`** (preserve custom rules):
   ```bash
   git-agent init --gitignore
   ```
3. **Full initialization** (both scopes and `.gitignore`):
   ```bash
   git-agent init --scope --gitignore
   ```

Report the updated configuration status upon completion.

CLI Reference: `{{PKG_DIR}}/references/cli.md`
