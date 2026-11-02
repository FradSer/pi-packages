# @fradser/pi-monitor

## 2.3.2

### Patch Changes

- 8662e95: Use additive run-start prompt contributions instead of complete prompt overrides. Do not use custom messages for context injection. Handle custom startup without a user prompt. Keep unrelated workflow records and authorization checkpoints.
- e86a44f: Apply pipe backpressure during output bursts, preserve physical matching-line
  boundaries, and bound aggregate captures before worker IPC with explicit
  truncation diagnostics. Use monotonic durations and reclaim partial matcher
  startup failures. Return typed Pi codemode results and reject pre-cancelled
  invocations before spawning commands. Include the authoritative best-practice
  comparison in the package.
- e86a44f: Build injected execution advice from current active tools each turn. Recommend optional codemode batching only when codemode and monitor_start are enabled, and bash grouping only when bash is enabled; otherwise use direct monitor calls. Preserve safety/history rules and host tool selection, and document capability-specific prompt costs.
- e86a44f: Reduce opted-in compact direct valid-success replies to explicit status, every payload/capture and any zero exit code, correlating through the native tool-call envelope. Keep full structured/UI metadata and complete reports for asynchronous notifications, failures and integrity warnings. Consolidate repeated guidance and schema descriptions and document short-command cost measurements. Omit guidance for host-disabled unused monitor tools while preserving it for restored results and summaries.
- e86a44f: Add optional exit-confirmed completion for finite workflows, rejecting invalid captured JSON and preserving later failure outcomes. Reduce prompt/schema overhead and duplicate capture text with exact-value aliases while preserving structured results. Keep diagnostic order by collapsing only adjacent repeats, and document native accuracy cases and measured token tradeoffs.
- e86a44f: Inject execution choices for grouped small bash commands, compact monitor contracts, available codemode batching and explicit dependency ordering. Require complete necessary payloads and failure details while retaining authority, deadline, integrity and delivery guidance. Update the batch example to preserve full failed terminal results and document fixed prompt overhead.
- e86a44f: Preserve valid JSON C1/DEL characters and Unicode line separators in model-facing reports by escaping them before terminal display cleanup. Add native payload accuracy probes, Unicode JSONL regressions and expanded token comparison documentation.
- e86a44f: Show only non-redundant fields in the expanded monitor start band.
  
  Drop the constant `terminal · pending at start` row, because the row already
  uses pi-kit's pending role. Drop the `cwd` row, because `monitor_start` has no
  cwd parameter and the value always equals the session cwd. Drop the monitor id
  row, because the model-facing result already carries `monitor_id` for
  `monitor_stop` and the `/monitor` console keeps ids for inspection.
  
  Show `Completion` and `Timeout` only when they differ from their defaults. A
  default start now expands to the stored command and its success and failure
  contracts.
  
  Give the started band its own `Label: value` vocabulary with an uppercase first
  letter on every label. A scalar field keeps the value beside its label. The
  command keeps the label alone on its row and its shell syntax below it.
  
  Highlight the command with pi's `highlightCode` under the active theme, so its
  keywords, strings and operators carry the user's colors. The command is
  sanitized before it reaches the highlighter.
  
  Use the same field-name vocabulary in the terminal event band and the stop row,
  so every expanded monitor field reads `Label: value` with an uppercase first
  letter. The row head keeps the shared pi-kit ` · ` separator between the
  outcome and the description.
  
  Attribute what ended every run. Record the completion mode and, when the
  contract rather than the process ended the run, the cause. A match-mode success
  never reads like a finished command, and its compact direct reply never
  collapses into a bare `status=success`. State the matched line as the contract's
  own evidence, and reference it when a result or capture already carries it.
  
  Name the next actor once a run does not pass. A `next=` line states that actor's
  next move for the cause, while a passing run carries evidence instead. The
  terminal row omits the monitor ID, which the `/monitor` list keeps as its
  selection key.
  
  Give the `/monitor` console the same vocabulary, the same highlighted command
  block and the same contract names as the lifecycle rows. The console spends no
  detail row on a description its list row already shows.
- e86a44f: Add optional compact reports with reversible repeated-text payload encoding while keeping complete bounded structured results and integrity diagnostics. Reduce redundant prompt/schema descriptions and document the measured routing limits versus native bash.
- e86a44f: A result sentinel now resolves the monitor whether or not it ends with a newline, and the `monitor_stop` disclosure stops rewriting the session tool allowlist when nothing changed.
  
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
- e86a44f: Keep monitor deadlines responsive by evaluating JavaScript result contracts in
  interruptible workers with bounded queues. Match unterminated tails independently
  for stdout and stderr, preserve diagnostics on timeout and stop, and await process
  group escalation and worker termination even after a monitor leaves the active list.
  Natural shell completion also reclaims remaining descendants in its process group.
  
  Return terminal results directly for mixed and nested Pi v1 tool batches; retain
  one asynchronous terminal notification per monitor-only UI call. Correlate direct
  and custom results with cross-instance unique monitor IDs, render synchronous
  outcomes truthfully, and validate development against Pi v1.0 with its Node baseline.
  
  Bound the monitor console by terminal dimensions, preserve selection, hide logs
  until requested, and route paging keys through Pi's focused overlay API.
  Goal completion evidence uses structured monitor status, ignores pending starts,
  and correlates modern IDs while preserving historical counter-based records and
  the chronological position of updated outcomes.
  
  Honor append-only context edits when collecting goal evidence: omitted receipts
  and assistant calls contribute no observations, replacements change only content,
  and original role and terminal metadata remain authoritative. Retain raw receipt
  coverage across compaction and preserve last-edit semantics.
- e86a44f: Keep monitor startup rows consistent with shared pi-kit geometry and native pending styling. Show effective completion, timeout and working directory before the full command and result conditions, preserving startup configuration for restored views without enlarging model-facing acknowledgements or structured schemas.
- e86a44f: Keep terminal outcomes visible with matching error/neutral/success styles, prioritize failure evidence, preview large values with a complete console view, and bound parallel activity rows to the terminal height. Preserve model-facing reports and structured payloads.
- e86a44f: Keep terminal state visible before long console descriptions, expose all keys in
  scrollable help with a width-aware footer, and refresh running human-only output
  while the console is open. Clear refresh timers when the overlay closes.
  
  Decode Kitty and xterm printable shortcuts through Pi v1 APIs while ignoring releases and
  control-modified input.
- 53cb34f: Stop `setActiveTools` toggle writes from deactivating tools the harness has not published yet.
  
  `setActiveTools` is an allowlist write: the caller passes the complete set the
  model may call, and anything absent is deactivated for the rest of the session.
  Every extension that toggled a tool read the active-tool snapshot, adjusted it,
  and wrote it back, so a snapshot that had not yet reported an extension's own
  registrations silently erased them. `pi-matt-pocock` then kept delivering routing
  prompts that name `matt_pocock_workflow`, instructing the model to call a tool it
  could not see.
  
  `@fradser/pi-kit` gains `setOwnedTools`, which re-asserts the extension's own
  tools instead of trusting the snapshot, and all five call sites now use it:
  `pi-matt-pocock`, `pi-monitor`, `pi-utils` sessions and worktree-session, and
  `@fradser/pi-agent-teams`' worker disclosure. Repeated identical writes are now
  idempotent rather than accumulating a duplicate entry.
- Updated dependencies [e86a44f]
- Updated dependencies [e86a44f]
- Updated dependencies [ff9b7ff]
- Updated dependencies [2bba220]
- Updated dependencies [426ef90]
- Updated dependencies [6603d43]
- Updated dependencies [e86a44f]
- Updated dependencies [e86a44f]
- Updated dependencies [6416992]
- Updated dependencies [fc0d801]
- Updated dependencies [53cb34f]
- Updated dependencies [ceb8e23]
- Updated dependencies [842b92e]
- Updated dependencies [b3daa7f]
- Updated dependencies [e86a44f]
- Updated dependencies [e86a44f]
- Updated dependencies [842b92e]
- Updated dependencies [e86a44f]
- Updated dependencies [53cb34f]
- Updated dependencies [53cb34f]
  - @fradser/pi-kit@0.6.0

## 2.3.1

### Patch Changes

- Updated dependencies [52e25f9]
  - @fradser/pi-kit@0.5.1

## 2.3.0

### Minor Changes

- 80aef33: Show running monitors as above-editor live activity rows through pi-kit's shared widget instead of a footer status entry. Each running monitor contributes one row (`monitor · <description>`, Pi's native spinner cadence) that appears while the agent is idle waiting for the terminal result and disappears with the last terminal result or stop; the footer below the input no longer carries a monitor waiting count.
- 7ef0fee: Let `monitor_start` omit `description`: the monitor derives a bounded human label from the command (whitespace collapsed, leading `sh -c` wrapper dropped, 60 characters maximum). Expanding the startup row now shows the success contract and any failure contract beside the command and monitor id, and the tool guideline replaces "declare the terminal result before starting" with explicit field roles so the description stops carrying the sentinel text.
- e0fd224: Remove the default bash tool-call guardrail. Monitor usage is now guidance-only, so native bash commands are no longer intercepted or required to use an allow-sync suffix.

### Patch Changes

- 9cabb0d: Bump every package by one patch version.
- 6d21149: Remove prompt text that duplicated each tool's own description. The isolated-research section keeps its trigger and no longer restates the child process mechanics, the monitor section keeps its behavior rules and no longer repeats the result-pattern, buffer, timeout, and notification mechanics, and the workflow gateway description no longer enumerates standalone capabilities that the injected catalog already lists. Agent Teams no longer advertises a template-creation action that does not exist, and its dead leader-tool disclosure hook and call sites are removed.
- 919504f: Wrap custom transcript lifecycle messages in host ToolExecutionComponent so mouse click toggling works symmetrically with tool result rows.
- 5b4f51b: Align tool lifecycle TUI styling with Pi native tokens: partial results render on toolPendingBg with warning accents, settled results on toolSuccessBg with success accents, and errors on a symmetrical toolErrorBg band whose subject is the first error line with remaining lines as expandable details (no duplicated subject). Remove the renderError escape hatch so every consumer error renders through the shared band, and style interactive model-picker query input in native blue
- 552a083: Unify every transcript row on one pi-kit mechanism. Kit gains `bindLifecycleRenderers` (geometry bound once per extension: shared expand hint, wrapping, and empty call), `contentDetailLines`, the `label · value` body vocabulary (`fieldLine`/`fieldBlock`), `displayText`, and handle scrubbing (`scrubHandles` with an injectable resolver). All packages render tool and message rows through the bound renderer: no call site can drop the expand hint or wrapping anymore, expanded bodies share one dialect, and runtime handles never reach human text (agent Work/session handles become names and subjects; monitor keeps its functional monitor id). Model-facing tool content is unchanged.
- efd5641: Make pi-kit own the whole live-activity status row, so no package can drift. The widget now formats the identity itself — bold in pi-kit's stable per-name accent palette, the same one `@name` segments use in report rows — and replaces the free-form `formatIdentity`/`formatActivity` hooks with one closed vocabulary: `activityFormat: "plain"` (muted, literal, unchanged default) or `"markdown"` (one sanitized line through pi-tui's Markdown with the injected theme's native markdown tokens; foreign ANSI is stripped, a streamed fence line is dropped, activity without visible width leaves an identity-only row, and the widget row truncates with `fit`). `renderLiveActivityIdentity`, `liveActivityMarkdownTheme`, and `renderLiveActivityMarkdown` are exported so console rows render identity and activity the same way instead of reimplementing either one.
  
  Context research and agent-teams teammate rows both request markdown activity: identified rows stop being colorless or warning-colored, well-formed markdown renders with the theme's tokens instead of literal markup, and status rows above the editor are now the same language in every package. agent-teams' console delegates to the shared renderer with a passthrough theme instead of keeping a second markdown implementation, and its roster, board, and report rows use the same per-agent accent for names and ids instead of a status-flavored palette. Every package that mounts a live widget is republished so it picks up the new pi-kit.
- Updated dependencies [b0231e3]
- Updated dependencies [ac83f4e]
- Updated dependencies [9cabb0d]
- Updated dependencies [919504f]
- Updated dependencies [bcb0054]
- Updated dependencies [efd5641]
- Updated dependencies [919504f]
- Updated dependencies [274cc90]
- Updated dependencies [28bdae2]
- Updated dependencies [707c4c5]
- Updated dependencies [5b4f51b]
- Updated dependencies [b0231e3]
- Updated dependencies [552a083]
- Updated dependencies [efd5641]
  - @fradser/pi-kit@0.5.0

## 2.2.0

### Minor Changes

- 006c715: Provide model-facing start acknowledgements with `monitor_id`, deliver terminal results synchronously in print/json modes without custom messages, and add `waitForTerminal` on `MonitorManager`.
- 38110c7: Add deterministic tool_call guardrail to intercept long-running and high-timeout bash commands (such as firmware flashing and SSH pipelines) with actionable monitor_start recipes.

### Patch Changes

- 548363d: Include terminal status in monitor event row titles so collapsed and expanded views display `[monitor] event · <description> · <status>`.
- ec7d764: Adopt static tool lifecycle renderers and computeScrollWindow in consumers, remove unused pi-kit exports, and restore strict local typecheck.
- 92944c1: Apply progressive tool disclosure across runtime packages. State-dependent capabilities are now hidden until their workflow state is active, and continual-learning no longer couples its guardrails to Matt Pocock workflow state.
- fab8160: Unify package TUI notifications, lifecycle rows, panels, and widgets through shared pi-kit rendering abstractions.
- Updated dependencies [ec7d764]
- Updated dependencies [b28ef2d]
- Updated dependencies [fab8160]
  - @fradser/pi-kit@0.4.2

## 2.1.1

### Patch Changes

- Updated dependencies
  - @fradser/pi-kit@0.4.1

## 2.1.0

### Minor Changes

- 02ec642: Add bounded monitor timeouts. `monitor_start` accepts `timeout_ms` and emits a terminal `timeout` result after the deadline, stopping the process group instead of waiting indefinitely when an external CLI or API is unavailable.

### Patch Changes

- dcf3806: Fix a crash when lifecycle tool rows render with pi's class-based Theme: extracting `theme.bg` into a local and calling it unbound lost the receiver, so any teammate/worktree tool result row threw `TypeError: Cannot read properties of undefined (reading 'bgColors')` (uncaughtException exiting pi). Lifecycle renderers now call theme methods through their receiver, with class-based-theme regression coverage. Unify the report-row visual language in pi-kit: every lifecycle row and collapsed teammate-message row share one full-width `customMessageBg` band (blank band row above/below, one-column inset), a `customMessageLabel`-colored bold `[tool] label ·` prefix, and per-teammate accent colors from pi-kit's stable palette applied to @name segments. Teammate report rows render `[message] from @name · <key> to expand` through the shared `renderAgentMessageBand` abstraction instead of their private Box, and agent startup rows use the explicit `[agent] @name started · task` shape. Remove the hard 80-character task-name cap so lifecycle rows truncate only at the actual terminal width; fixed session panels keep an explicit local width bound. Truncated band rows no longer lose the band background: truncating a styled row injects a full SGR reset (\x1b[0m) before the ellipsis that also cleared the customMessageBg, so pi-kit now re-applies the background immediately after every reset — the ellipsis and trailing padding keep the same band color as the preceding text.
- 6664765: Collapse repeated source-labelled diagnostic lines in terminal monitor results and include their occurrence counts to keep timeout and failure reports concise.
- dcf3806: Clarify monitor guidance so quick, low-output information commands run directly while noisy, long-running, or asynchronous work uses `monitor_start`.
- Updated dependencies [fde16ae]
- Updated dependencies [dcf3806]
- Updated dependencies [dcf3806]
- Updated dependencies [dcf3806]
- Updated dependencies [a7fbc11]
  - @fradser/pi-kit@0.4.0

## 2.0.5

### Patch Changes

- d37028f: Unify collapsible event rows on the shared pi-kit expand hint and fix the teammate shutdown label: `teammate_shutdown` now renders one `[agent] event · @name shut down` row (previously mislabeled as a monitor event) whose collapsed line appends the same dim ` · <configured key> to expand` hint as teammate report rows, with the shutdown details (exit code, released tasks, usage) revealed behind expansion. `formatExpandHint` moves the hint language into `@fradser/pi-kit`, replacing the hand-rolled variants in agent-teams, monitor, and utils. Leader `send_message` adopts the same single-row lifecycle pattern: the call slot renders nothing and one `[message] to @name · delivered|queued` row carries the outcome (plus a dim stalled-duration suffix), replacing the duplicated call-plus-sentence transcript rows. `task_create` gets the same treatment with a `[board] created · <subject>` row; all leader tool renderers now key failures off pi's render-context `isError` flag instead of the result object. A teammate's completion entry ("Teammate @name finished.") is announced once per spawn incarnation: reports now carry the spawn identity, so repeated terminal-status messages from one resident render as ordinary report rows instead of duplicate finished lines, while a respawned teammate of the same name announces again.
- Updated dependencies [d37028f]
  - @fradser/pi-kit@0.3.0

## 2.0.4

### Patch Changes

- 50c45ff: Share compact tool lifecycle labels through pi-kit and standardize monitor startup and terminal event rendering.
- Updated dependencies [50c45ff]
- Updated dependencies [7ad11b4]
  - @fradser/pi-kit@0.2.0

## 2.0.3

### Patch Changes

- Standardize runtime package entry points on package-root `index.ts` modules. The monitor status is also rendered through Pi's native footer so it appears below the directory and usage lines.

## 2.0.2

### Patch Changes

- 3c88ab4: Introduce `@fradser/pi-kit` as the shared internal runtime package and remove duplicated TUI, message, and model-selection helpers across consumers:
  
  - Spinner frames/interval (`PI_SPINNER_FRAMES`, `PI_SPINNER_INTERVAL_MS`) come from pi-kit in agent-teams, memory, recap, and vision.
  - The overlay/console theme style language (`createPiThemeStyle`) comes from pi-kit in btw and agent-teams; `BtwOverlayStyle` aliases `PiThemeStyle`.
  - Message text extraction (`extractTextContent`) comes from pi-kit in btw, recap, vision, utils, and agent-teams.
  - Model selection (`parseModelRef`, `modelRef`, `modelLabel`, `sortModels`, `selectModelFromMenu`, `enterModelFromInput`) comes from pi-kit in memory, recap, and vision.
  - monitor's hand-rolled escape-key check now uses pi-tui's `matchesKey(data, Key.escape)`.
  
  Also fixes a packaging/loading bug in `@fradser/pi-memory`: `config.ts` moved into `extensions/` (it was outside the shipped `files` and the directory-glob the extension loader used), and the `pi.extensions` entry now points at `./extensions/inject-memory.ts` so pi loads exactly the factory file and treats `config.ts` as a helper module.

## 2.0.1

### Patch Changes

- f4fccb1: Republish all published package versions through GitHub CI to align with current release flow and regenerate their release metadata after version comparison.

## 2.0.0

### Major Changes

- e55e25e: Replace raw progress-log streaming with result-contract monitoring. `monitor_start` now requires `result_pattern`, supports an optional `failure_pattern`, scans stdout and stderr without injecting progress into model context, and emits one structured terminal result with a bounded diagnostic tail. Remove the model-facing `monitor_read` output reader so agents wait for the contracted terminal notification instead of polling.

## 1.0.0

### Major Changes

- e09c395: Replace raw progress-log streaming with result-contract monitoring. `monitor_start` now requires `result_pattern`, supports an optional `failure_pattern`, scans stdout and stderr without injecting progress into model context, and emits one structured terminal result. Add `monitor_read` for bounded, on-demand diagnostics and retain recent completed monitor output for inspection.

## 0.1.1

### Patch Changes

- 1c5e807: Rename to @fradser/pi-monitor and publish for the first time.
