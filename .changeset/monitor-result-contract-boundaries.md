---
"@fradser/pi-monitor": patch
---

A result sentinel now resolves the monitor whether or not it ends with a newline, and the `monitor_stop` disclosure stops rewriting the session tool allowlist when nothing changed.

**A sentinel does not need a trailing newline**

`MonitorManager` evaluated the contract per complete line, and a line only became
complete at a `\n` or at process `close`. A command that printed a finished
sentinel without a newline and then kept running therefore produced no terminal
result at all until the process exited: the monitor the package documents for
"wait until the server is ready" could not report ready, and a long-lived command
only ever resolved through `timeout_ms`. Measured on the reference machine, with
an otherwise identical contract:

```
printf '__DONE__ 3\n'; sleep 3   -> success @ 1010ms
printf '__DONE__ 3';  sleep 3   -> success @ 3015ms   (process exit, not the sentinel)
```

Both stdout and stderr now get an idle tail check: when new bytes leave an
unterminated trailing line and then go quiet for `TAIL_MATCH_IDLE_MS` (150ms),
that line is evaluated against `result_pattern` and `failure_pattern` with the
same precedence a complete line gets. The partial buffer is never committed by
the check, so a writer that pauses mid-line loses nothing — the joined line still
matches when its newline arrives — and the retained log still records the full
line. Idle windows are independent per source; within one line a
`failure_pattern` still wins over a `result_pattern`.

The 150ms window is the trade: long enough that a writer pausing mid-line does
not look like a finished line, short enough that a ready signal resolves while
the command keeps running. A sentinel whose *prefix* already satisfies the
contract and whose writer then pauses longer than the window resolves early —
the same judgement every line-oriented matcher makes, now bounded and documented
rather than accidental.

**The disclosure writes only on a state transition**

`monitor_stop`'s progressive disclosure ran `setOwnedTools` at `session_start`
and on every terminal event, including events that did not change whether a
monitor was running. `setActiveTools` is a session-wide allowlist write, so each
of those redundant writes was another chance to deactivate a tool the harness had
not published yet — the failure mode pi-kit's `setOwnedTools` was introduced to
close, re-opened by writing more often than necessary. The extension now tracks
the state it last wrote and writes only when the running-monitor state actually
flips: the baseline at `session_start`, the first monitor, and the last monitor
leaving.

**The delivery path now follows `ctx.hasUI`**

`monitor_start` decided between asynchronous delivery and waiting inside the call
with a hardcoded `mode === "print" || mode === "json"` test. That made RPC mode an
accident: a session with a real UI host that paints the lifecycle row and the
terminal message got the interactive path for no stated reason, and a future
headless mode would have silently inherited the wrong one. The harness already
answers the UI question — `ExtensionContext.hasUI` is documented as "true in TUI
and RPC modes" — so the extension reads it, with a mode fallback for hosts that
omit the flag. Pi v1 additionally requires monitor-only batches for asynchronous
delivery; mixed or nested calls wait for the terminal result inside the tool.

**The static test debt is paid down**

Twenty-seven of the suite's tests asserted on `src/*.ts` text: `assert
'child?.on("close"' in manager`, `assert 'placement: "aboveEditor"' not in
extension`, and so on. They pass while behavior regresses and fail on harmless
refactors, and several of them duplicated a behavioral test that already existed
— `test_monitor_start_renderer_uses_the_shared_lifecycle_band` had been asserting
the exact pi-kit band tokens for some time while the source-text version sat
beside it. Seventeen are gone, replaced by five tests that drive the extension
through its own registered surface:

- the registered tool, renderer, and command surface, and the absence of any
  `tool_call` or `tool_result` hook or skills directory;
- the delivery split, driving `tui`/`rpc` and `print`/`json` through
  `monitor_start.execute` and asserting `terminate` and the returned terminal
  report;
- `monitor_stop`'s two rejection messages and its success result, from the tool
  rather than from its source;
- the `/monitor` console: it paints through `ctx.ui.custom`, lists the running
  monitor, closes on `q`, registers no global input listener, writes no footer
  entry, and falls back to a notification where no console is available. A
  description carrying a raw ESC and a raw 8-bit C1 sequence comes back as
  display text — removing `safeDisplayText` from that row makes the test fail, so
  the sanitization claim is now observed rather than asserted;
- the tool description budget, read off the registered tool.

Five existing behavioral tests gained the assertions that only the static versions
made: the empty call line, the absence of a native bullet and a hard-coded
`Ctrl+O` in a rendered row, the injected guidance's field roles read from
`promptGuidelines`, the delivery shape (`customType`, `deliverAs`) and the
compact `key=value` shape of the delivered message, and a `setStatus` trap on the
activity widget. Eight static tests remain, all of them packaging or schema facts
that no runtime call can observe: manifest keywords, entry points, peer
dependencies, the absent skills directory, absent Claude-only artifacts, two
TypeBox schema shapes, and the exported bound constants.

One fixture correction fell out of the delivery change: three tests passed
`{ cwd }` as the session context and expected interactive behavior, which only
worked because the old test read a mode list those fixtures never mentioned. They
now declare `mode: "tui", hasUI: true` — the session they were simulating all
along.

**Also**

- `handleLine` no longer threads a `_processAlreadyClosed` parameter that nothing
  read, and `drainFinalBuffers` no longer takes it either.
- `MonitorManager.clearTimeout` was renamed `clearTimeoutTimer`. The old name
  shadowed the global inside the class, so `this.clearTimeout(monitor)` read like
  a bug at both call sites.

**Verification**

- `packages/monitor/tests/` (42 tests) covers the new behavior from the real
  manager: `test_unterminated_sentinel_resolves_while_the_command_keeps_running`
  starts `printf 'READY url=…'; sleep 20` and requires one `success` terminal
  with the named capture resolved in under 2s, which fails without the idle check
  because no result arrives at all;
  `test_sentinel_split_by_a_write_pause_still_matches_the_joined_line` sends the
  sentinel in two writes a full second apart so the pause outlasts the idle
  window, pinning the decision not to commit the buffer;
  `test_monitor_stop_disclosure_writes_only_on_running_state_transitions` counts
  `setActiveTools` calls through a fake host and requires one write per flip and
  none for a second concurrent monitor or for stopping one of two.
- `test_unterminated_buffer_matches_before_process_exit` is gone. It ran
  `printf 'READY url=…'`, a command that exits immediately, so the match happened
  at `close` — the opposite of what its name claimed, and the reason the gap
  above survived a green suite. `test_unterminated_final_sentinel_matches_during_close_once`
  still covers the close path, and the new test covers the live one.
- The remaining static tests were each checked against a behavioral test for the
  same contract, and the redundant ones were removed rather than kept as
  belt-and-braces: the `close`-not-`exit` and `SIGTERM`→`SIGKILL` internals are
  covered by `test_sigkill_escalates_to_term_resistant_descendant_after_shell_closes`
  and `test_session_shutdown_waits_for_sigkill_escalation_before_parent_exit`,
  and the band, hint, and `label · value` vocabulary are covered by the two
  renderer tests that assert the real rows.
- `pnpm typecheck` and `pnpm --dir packages/monitor pack --dry-run` are clean.
- Against the real `pi` binary: `pi --print` loading this extension with
  `printf "booting\n"; printf "READY port=3000"; sleep 25` and
  `result_pattern: READY port=(?<port>\d+)` returned `status=success`,
  `capture.port=3000`, `elapsed=158ms` while the 25s sleep was still in flight.
  A `pi --mode rpc` session loading this extension with a second package still
  shows `monitor_stop` entering the active-tool list while a monitor runs and
  leaving when it terminates, with the other extension's tools intact, and the
  terminal result still wakes exactly one turn.

**Not changed**

- RPC monitor-only batches keep asynchronous delivery. A follow-up Pi v1 audit
  found that mixed and nested batches need to return terminal data inside the
  call, because every result must request termination for a batch to end.
- The previous backtracking probe did not establish a worst-case bound. A
  counterexample blocked the main thread and its timeout. Contract evaluation
  now runs in an interruptible worker with bounded queuing; see the follow-up
  runtime and delivery safety changeset for the verified behavior.
