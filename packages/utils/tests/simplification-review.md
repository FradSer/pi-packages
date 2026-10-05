# Utils simplification

## Scope

Preserve command contracts. Keep worktree isolation and live-session security branches unchanged.

## Findings and changes

- Continuation reads a bounded tail but previously missed a complete entry larger than that window.
- The regression test fails before the fix. The reader now uses its documented full-read fallback.
- Direct continuation now awaits delivery. Tests check promise-host rejection and replaced-session delivery failure.
- Ordinary Pi sendMessage returns void. These tests do not prove ordinary Pi asynchronous failure propagation.
- Continuation tests exercise registered commands and events instead of source strings.
- Sessions tests share a runtime runner with a 30-second timeout. Redundant source checks are removed.
- The two test files and shared runner total 735 lines, compared with 969 lines before this change.

## Latest verification

- Package suite: 90 passed and 52 subtests passed.
- Root entry and prompt-budget checks: 11 passed.
- Root TypeScript check: passed.
- Utils pack dry-run: passed. Test helpers are not included in the package.
- Installed Pi print-host worktree reproduction: passed in an isolated temporary repository with an offline provider.
- Changed-file whitespace check: passed.
- Installation check: blocked by 13 unrelated missing global package declarations. Global settings remain unchanged.

## Limits

Interactive TUI behavior is not verified. The print reproduction covers worktree session replacement, not continuation provider recovery.
The tests use a fake Pi host for continuation behavior. No external model request runs.
Independent review passed without blockers. The reviewer identified a replaced-session failure coverage gap.
The reload test now covers an unseen disk tip, an incomplete replaced branch, and rejected marker delivery.
The affected continuation suite passes again: 6 passed.
