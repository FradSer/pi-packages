#!/usr/bin/env bash
# Fresh proof for the completion check: one labelled line per condition, each
# with its own exit code, so nothing is masked by a pipeline.
cd /Users/FradSer/Developer/FradSer/pi-packages || exit 2
fail=0
line() { printf '%-46s %s\n' "$1" "$2"; }

out=$(python3 -m pytest packages/tasks/tests/ packages/agent-teams/tests/ packages/subagents/tests/ -q 2>&1)
code=$?
summary=$(printf '%s' "$out" | grep -E '^[0-9]+ (passed|failed)|failed,' | tail -1)
line "combined pytest exit" "$code"
line "combined pytest result" "${summary:-NO SUMMARY}"
[ "$code" -eq 0 ] || fail=1

out=$(pnpm typecheck 2>&1); code=$?
line "pnpm typecheck exit" "$code"
[ "$code" -eq 0 ] || fail=1

out=$(pnpm --dir packages/tasks pack --dry-run 2>&1); code=$?
listed=$(printf '%s' "$out" | grep -c '^src/')
line "pack dry-run exit" "$code"
line "pack dry-run sources listed" "$listed"
[ "$code" -eq 0 ] || fail=1

old=$(grep -c 'ok: false, error: string\|ok: false, reason: string\|applied: false, reason?: string' packages/tasks/src/store.ts)
hand=$(grep -c 'ok: false, refusal: "' packages/tasks/src/store.ts)
line "old refusal shapes in store.ts" "$old"
line "hand-written refusal literals" "$hand"
[ "$old" -eq 0 ] && [ "$hand" -eq 0 ] || fail=1

sites=$(grep -c 'return refuse(' packages/tasks/src/store.ts)
claim=$(grep -c 'return refuseClaim(' packages/tasks/src/store.ts)
line "refuse() call sites" "$sites"
line "refuseClaim() call sites" "$claim"
[ "$sites" -gt 0 ] && [ "$claim" -gt 0 ] || fail=1

# Consumer-wide: no package may still read `.error` off a task-store result.
consumers=$(grep -rn 'created\.error\|\.error ?? "").*refusal' packages/tasks/src packages/agent-teams/src packages/subagents/src 2>/dev/null | wc -l | tr -d ' ')
line "consumers reading a store .error field" "$consumers"
[ "$consumers" -eq 0 ] || fail=1

legacy=$(grep -rn 'refusal === "unknown"\|refusal: "unknown"' packages/tasks/src packages/agent-teams/src 2>/dev/null | wc -l | tr -d ' ')
line "consumers on the retired refusal code" "$legacy"
[ "$legacy" -eq 0 ] || fail=1

line "OVERALL" "$([ "$fail" -eq 0 ] && echo PASS || echo FAIL)"
exit "$fail"
