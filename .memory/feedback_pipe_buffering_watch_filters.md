---
name: pipe-buffering-watch-filters
description: grep/sed/awk block-buffer when stdout is a pipe — a monitor watching `script | grep -v` sees nothing for minutes; use script-native exclusion or --line-buffered
type: feedback
---

Never pipe a watch/event script's stdout through `grep -v` / `sed` / `awk` to drop lines. Those tools block-buffer when their stdout is a pipe: lines stall in the filter's buffer until ~4 KB accumulates or the process exits. The downstream monitor receives nothing in the meantime.

**Why:**
Live incident on Code Terrier PR #122: monitor_17 ran `review-loop.sh | grep -v node=A | grep -v node=B` and showed `0 retained, 0 dropped` for 20+ minutes while a new code-terrier review had already been emitted by the script — the line sat in BSD grep's stdio buffer. Verified with a minimal repro: macOS BSD grep 2.6.0 delivers zero bytes through a two-stage `grep -v` chain until the pipeline exits; `grep --line-buffered` fixes it. The pi monitor side is correct (it consumes chunks as they arrive) — the trap is purely in the command composition. The `grep -v` chain existed only because `review-loop.sh` had no way to suppress already-triaged comments on a mid-PR restart (every run re-surfaces history since PR creation).

**How to apply:**
1. Use native exclusion instead of downstream filters: `review-loop.sh` accepts `EXCLUDE="<node-id> ..."` env and repeatable `--exclude <node-id>` (merged), checked in `emit_comment` before dedup. BDD coverage: `skills/features/review-pr-watch.feature` + `tests/test_review_loop.py` (fake `gh` shim).
2. If a filter stage is ever unavoidable: `grep --line-buffered`, `sed -l`, or `awk '{ print ...; fflush() }'`.
3. Diagnostic signature: a `running` monitor with `0 retained, 0 dropped` while the source clearly produced output = a buffered pipeline stage, not a monitor bug. Check `ps` for intermediate grep/sed/awk processes.
4. This is documented in `skills/skills/review-pr/references/review-loop.md` (Excluding already-triaged comments on restart) and in `packages/monitor` (using-monitor SKILL.md + README diagnostics).

**Related:** [[monitor-optimization]] [[pi-package-conventions]]
