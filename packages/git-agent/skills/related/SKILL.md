---
name: related
description: Mines git history to find files and test suites that historically change together with specified target files (co-change relations). Use before making changes or running tests to discover coupled code.
---

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

Report the historically coupled files and tests to guide code edits and test suite execution.

CLI Reference: `../../references/cli.md`
