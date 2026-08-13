# git-agent — Related files & tests procedure

> **Inline procedure.** Embedded verbatim into the follow-up message by the
> `/git-agent` menu ("Related files & tests") via `pi.sendUserMessage` — it is
> not a skill and the menu delivers it inline. `{{PKG_DIR}}` is
> substituted with the package dir at send time.

Mine git history to find files and test suites that historically change
together with the given target files (co-change relations).

## Execution

Execute `git-agent related` to query co-change relations (offline and read-only):

1. **Find coupled files**:
   ```bash
   git-agent related <file-paths...>
   ```
2. **Find related tests**:
   ```bash
   git-agent related --tests <file-paths...>
   ```
3. **Structured JSON output**:
   ```bash
   git-agent related -o json <file-paths...>
   ```

Report the historically coupled files and tests to guide code edits and test
suite execution.

CLI Reference: `{{PKG_DIR}}/references/cli.md`
