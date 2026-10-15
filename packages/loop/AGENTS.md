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
  candidates that code built. Never ask a model to write the repeated message.
- **Closed questions only**: use `askSystemOne` from pi-kit. Its question types are
  `noul`, `choice` and `score`; a generative answer is unrepresentable. Keep the
  criteria objects as the single source of truth for both the question and the
  answer validation, so a declared option cannot be rejected as unknown.
- **Fail closed**: a missing credential, an unspecified cadence, a low-confidence
  answer and an unknown answer key are reports, not guesses. `--until` needs a
  credential too, because Pi must judge the condition.
- **Delivery**: inject with `pi.sendUserMessage` so each repetition is a real user
  turn. Never use a custom message for the repetition itself.
- **Scheduling**: skip a tick whose previous repetition has not settled, and count
  it. Observe the promise `send` returns: a delivery that throws or rejects is
  reported as `undelivered` and ends the loop, because a repetition that never
  arrived cannot be judged. `stop()` is terminal and releases the timer. Start no
  timer in the extension factory.
- **Transcript**: one lifecycle row for the start, through
  `bindLifecycleRenderers` and `startedToolLifecycle`. Keep per-repetition status
  in `setStatus`, not in extra rows, because the injected turn already appears.
- **Bounds**: keep the interval between 1s and 1d, and bound the text sent for one
  stopping judgment.

## Testing Guidelines

`features/loop.feature` states the behavior. `tests/loop-core-fixture.ts` covers
the deterministic modules on a virtual clock. `tests/loop-decision-fixture.ts`
runs every Jev question against a real loopback endpoint, including the failure
classes; never stub the transport. `tests/loop-live-fixture.ts` drives the real
`pi` TUI with a scripted local provider. It proves the parameterized injection arrives as
`messageType: "user"`, and it pairs a met stop condition (0.95) with a
below-threshold one (0.3) so the threshold, not something else, is what ends the loop. Keep the fixture runs isolated: a disposable `HOME` and `PI_CODING_AGENT_DIR`, `PI_OFFLINE=1`, and no `TYPESAFE_API_KEY`. `tests/live_loop_rows.py` is the explicit-run terminal probe. Run it with `uv run --no-project --with pyte python packages/loop/tests/live_loop_rows.py`. It composes the real terminal with pyte and checks the start row and the status row at 120x40, after a live resize to 48x24, and by PageUp at 48x12. Keep the below-editor row read as `<verb> · <detail>` with no package tag.
## Safety

Never log or write the decision credential. Never send private session text to a
decision request without the user's request that caused it.
