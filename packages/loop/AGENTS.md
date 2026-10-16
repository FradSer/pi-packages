# Repository Guidelines

## Project Structure

`packages/loop/` publishes `@fradser/pi-loop`. The package-root `index.ts`
re-exports the extension from `src/index.ts`. `src/index.ts` owns the `/loop`
command, the native delivery, the session lifecycle and the transcript row.
`src/params.ts` parses the explicit flags, `src/duration.ts` owns interval
arithmetic, and `src/template.ts` owns the closed placeholder set.
`src/candidates.ts` builds the candidate lists and the deterministic text
assembly, `src/segments.ts` splits a free request into candidates, and
`src/decide.ts` owns every Jev question. `src/scheduler.ts` owns the repeating
timer. BDD contracts are in `features/loop.feature`; executable checks are in
`tests/`.

## Commands

Run focused tests from the repository root:

```bash
python3 -m pytest packages/loop/tests/ -q
pnpm typecheck
pnpm check:install
pnpm --dir packages/loop pack --dry-run
```

`pnpm typecheck` resolves `src/` only, so `tests/test_loop_hygiene.py` runs
`tsc -p packages/loop/tsconfig.tests.json` over the harnesses. Keep that check:
a harness import that Bun erases at runtime is invisible to every other gate.

## Style and Architecture

- **Determinism first**: parse flags, intervals, placeholders and text assembly in
  code. Send a request to Jev only where a real choice exists, and only over
  candidates that code built. Never ask a model to write the repeated message. A
  segment that only states a repetition count is the run limit, not a stopping
  condition: `isRunCountSegment` in `src/candidates.ts` excludes it from the stop
  candidates and `messageCandidates` strips it from the message. A measured run of
  the real service chose "3 times" as the stopping condition for four count-only
  requests before that exclusion existed (`tests/real-jev-accuracy.ts`). A count
  phrase inside a segment counts too: `stripRunCount` leaves it out of the message,
  so `/loop 输入3次Hi` repeats `输入Hi`, and `ResolvedLoop.messageStripped` makes the
  start line say so. Keep that rule for a free request: the count is scheduling
  metadata wherever it appears. Text stated with `--message` or after `--` is
  injected verbatim, because the user wrote it as the message.
- **Ask only what code cannot decide**: the message question runs only when the
  service's own answer shaped the text, which is the stopping-condition segment.
  Metadata this module matched itself — a schedule phrase or a count phrase — must
  never come back as a choice: offering the untouched request asked the service to
  repeat a decision code had already made, and a low-confidence answer to it
  refused the whole command (`/loop say hi * 3` failed with 0.22 < 0.30 against the
  live service). One question set per free request, and no paid question where the
  answer is already known.
- **Closed questions only**: use `askSystemOne` from pi-kit. Its question types are
  `noul`, `choice` and `score`; a generative answer is unrepresentable. Keep the
  criteria objects as the single source of truth for both the question and the
  answer validation, so a declared option cannot be rejected as unknown.
- **No cancellation**: a decision request carries no abort signal, because none
  reaches this code. Pi 1.2.0 passes `ctx.signal` to a hook that runs inside a
  turn, such as `turn_start` or `message_start`, and `undefined` to an extension
  command and at `agent_settled`. The client's own timeout bounds each request.
  Measure the host again before you add a signal to `src/decide.ts`.
- **Fail closed**: a missing credential, a low-confidence answer and an unknown
  answer key are reports, not guesses. `--until` needs a credential too, because Pi
  must judge the condition. An unnamed cadence is decided only when a run count
  is never a refusal: the plan takes `DEFAULT_COUNT_INTERVAL_MS` from
  `src/duration.ts` — five minutes, because a repetition is a whole agent turn and
  a shorter tick only makes the loop skip ticks. The start notice says the cadence
  was assumed, so a defaulted cadence is never silent. `/loop 检查项目修改，总结`
  therefore runs until `/loop stop` or a stopping condition; never refuse a
  request for a cadence it left out.
- **Delivery**: inject with `pi.sendUserMessage` so each repetition is a real user
  turn. Never use a custom message for the repetition itself.
- **Scheduling**: skip a tick whose previous repetition has not settled, and count
  it. `send` returns void: Pi reports a turn that fails after acceptance on its own
  error channel, so the only refusal the loop could observe is the synchronous
  throw it raises for a stale captured API. Report that as `undelivered` and end
  the loop. The catch is defensive: `session_shutdown` stops a loop before Pi
  invalidates a captured API, which `tests/live_delivery_refusal.py` measures for
  `ctx.reload()` and `ctx.newSession()`. `stop()` is terminal and releases the
  timer. Start no timer in the extension factory. Only the loop's own repetition
  may be judged: `agent_end` compares the run's last user message with the pending
  injection, so a turn the user started, and a turn that was already running when
  a repetition was queued behind it, ask no stopping question. Keep that check:
  `tests/loop-command-fixture.ts` scenario `only-the-repetition-is-judged` covers
  both directions.
- **A free request reports itself first**: append one `loop-request` row at command
  time — `startedToolLifecycle("loop", request, { label: "request", subjectBlock:
  true, verbatimSubject: true })`, so the head row and the request text are separate
  rows — and write `Analyzing · <request>` to the status row before the decision
  request. Both come from one place: `announceRequest` and `showStatus` in
  `src/index.ts`. The flag form does neither, because it calls no model and starts
  directly. Keep the echoed text the user's own words: it is the request, not the
  resolved message.
- **Transcript**: one lifecycle row for the start, through
  `bindLifecycleRenderers` and `startedToolLifecycle`. Keep per-repetition status
  in `setStatus`, not in extra rows, because the injected turn already appears.
  The start line is a deliberate exception to the root guidance's send shape, and
  its placement is the reason. Every `/loop ...` arrives as a user turn, and the
  first repetition is queued behind that run, so a line sent from the command
  lands before the user's own input (`pi.sendMessage` with `triggerTurn` appends
  immediately; `deliverAs: "followUp"` preempts the run's queue and would put the
  line ahead of a repetition that is already queued). The line therefore waits in
  `startNotice` and is injected by the `before_agent_start` handler at the head of
  the next run, which is the run a repetition reaches. Measured on Pi 1.2.0: the
  resulting run is `system, user, custom, assistant`, and a start with
  `triggerTurn: true` drops the user's own command text from the run. The first
  repetition runs at start, so the line appears with it rather than an interval
  later.
- **Bounds**: keep the interval between 1s and 1d, and bound the text sent for one
  stopping judgment.

## Testing Guidelines

`features/loop.feature` states the behavior. `tests/loop-core-fixture.ts` covers
the deterministic modules on a virtual clock. `tests/loop-decision-fixture.ts`
runs every Jev question against a real loopback endpoint, including the failure
classes; never stub the transport. `tests/loop-live-fixture.ts` drives the real
`pi` TUI with a scripted local provider. It proves the parameterized injection arrives as
`messageType: "user"`, and it pairs a met stop condition (0.95) with a
below-threshold one (0.3) so the threshold, not something else, is what ends the loop. Keep the fixture runs isolated: a disposable `HOME` and `PI_CODING_AGENT_DIR`, `PI_OFFLINE=1`, and no `TYPESAFE_API_KEY`. `tests/loop-decision-fixture.ts` scenario `count-without-cadence` covers the
defaulted cadence on the wire, and scenario `only-the-repetition-is-judged` in
`tests/loop-command-fixture.ts` covers which settled turn is judged.
`tests/live_loop_rows.py` is the explicit-run terminal probe. Run it with `uv run --no-project --with pyte python packages/loop/tests/live_loop_rows.py`. It composes the real terminal with pyte and checks the start row and the status row at 120x40, after a live resize to 48x24, and by PageUp at 48x12. Keep the below-editor row read as `<verb> · <detail>` with no package tag.

`tests/live_delivery_refusal.py` is the explicit-run probe for the delivery refusal. It drives RPC mode, so an extension `notify` arrives as a structured record: run `uv run --no-project python packages/loop/tests/live_delivery_refusal.py`. It measures that all four replacements — `ctx.reload()`, `ctx.newSession()`, `ctx.fork()` and `ctx.switchSession()` — stop the loop through `session_shutdown` before any tick can call an invalidated API, and it keeps the control case that must still deliver turns. It does not measure whether some other host path could invalidate a captured API without that shutdown.

`tests/real-jev-accuracy.ts` is the explicit-run **paid** probe for accuracy, usage and cost: run `bun packages/loop/tests/real-jev-accuracy.ts` with `TYPESAFE_API_KEY` set. It spends real credits, resolves twelve labelled requests plus one `met` judgment, and reports per-question accuracy and tokens per case. `--from <saved run>` recomputes the summary without spending.
`tests/live_terminal_accessibility.py` is the explicit-run probe for real terminal rendering and assistive text. It needs macOS, Accessibility permission and Screen Recording permission, and it opens real Terminal.app windows: run `uv run --no-project python packages/loop/tests/live_terminal_accessibility.py`. It records OS screenshots of the window content and the terminal's accessibility text area at 120x40, 48x24, 48x12 and a fresh 48x12 window, excluding the title bar because this host's Terminal profile prints credentials there. VoiceOver speech output stays unverified.

## Safety

Never log or write the decision credential. Never send private session text to a
decision request without the user's request that caused it.
