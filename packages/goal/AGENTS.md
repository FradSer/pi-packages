# Goal Runtime Package Guidelines

Applies to `packages/goal/` (`@fradser/pi-goal`). All references below are
repository-relative.

## Read by Task

- The record, its normalization, and elapsed time: @packages/goal/src/record.ts.
- On-disk layout and path safety: @packages/goal/src/paths.ts.
- The event vocabulary and history paging: @packages/goal/src/ledger.ts.
- The sole mutation boundary: @packages/goal/src/store.ts.
- Continuation authorization: @packages/goal/src/scheduler.ts.
- Injected prompts, the capability note, and `/goal`'s seed:
  @packages/goal/src/prompt.ts.
- Pre-creation read-only research: @packages/goal/src/research.ts.
- Completion observations and provenance: @packages/goal/src/evidence.ts.
- Deciding whether the objective is met: @packages/goal/src/check.ts.
- Holding state, focus, and the check: @packages/goal/src/core.ts.
- The four tools: @packages/goal/src/tools.ts.
- Lifecycle handlers: @packages/goal/src/events.ts.
- Below-editor passive status row with whole-minute time: @packages/goal/src/dashboard.ts.
- The single `/goal` command: @packages/goal/src/commands.ts.
- Settings layering: @packages/goal/src/settings.ts.
- Behavior contract: @packages/goal/features/goal.feature.

## What a goal is not

A goal is one objective and one exit condition. Do not reintroduce a task tree,
a progress fraction, or a second opinion about whether the work is done. A task
list is a second answer to "is this met?", maintained by the model doing the
work, and the two contradict each other in exactly the state where the decision
matters.

Do not reintroduce an inspecting reviewer. The completion check is one tool-less
completion; `bash` must never be granted to it, because a shell can write
anything and that is what makes an empty tool grant worth having.

Research is material, not evidence. The research child gets `read`, `grep`,
`find`, and `ls` — never `bash`, never a write tool — and its findings may
enter the objective the model writes but never the completion-check prompt.
Findings reach disk only through `store.create`; a failed research attaches
no new findings and never blocks creation. The latest successful run replaces earlier findings. A session boundary clears pending findings. The research model setting is separate from
the check's, so each can be set alone.

## Behavior Boundaries

- The store is the only goal-record mutation boundary and the ledger module is
  the only appender. Both build on pi-kit (`writeJsonAtomic`, `appendJsonlLine`,
  `readJsonlBatch`, `createExclusiveJsonFile`); no other module may reach a
  pi-kit write primitive. Do not add a second path to disk.
- Goals belong to a thread. Restore only that thread's persisted reference.
  Never adopt project goals, including through legacy auto-selection settings.
  A record's threadId cannot change through resume. Legacy records require a thread entry.
- Register only `/goal`: bare input reads status; exact pause/resume/clear arguments manage the current goal.
  Other complete text supplies the objective and completion conditions. Never parse management verbs by prefix.
  Activation requires a matching accepted request at before_agent_start, never merely a void send call.
  A busy request with no goal being pursued is refused before intent is stored; one under way takes the
  text as a revision through the same writer as `update_goal`. Completion checks bind the scheduler generation.
- Status, tools, and the widget read fresh disk state. Paused goals do not accrue usage or run automatic checks.
  Resume must set the current scheduling owner and bind an idle context before reporting an authorized continuation.
- Authorization is a durable decision in the record, consumed exactly once by
  `claim`, which re-validates ownership, goal, generation, budget, allowance and
  deadline at delivery time. A timer, a settled turn, and a queued message are
  opportunities, never authorization. Keep arming and claiming separate.
- Productive continuation has no default run cap. Three no-work runs stop the empty loop.
  Three valid explicit final refusals pause with the last unmet condition and recovery advice.
  Stale, cancelled, or failed checker calls never consume that final-attempt count.
  Requirements revisions and explicit resume reset final failures. Never call pause completion.
- Decide completion and continuation at agent_before_settle, not the notification-only agent_settled event.
  Claim and accept a checkpoint before returning boundary entries and continue: true to Pi.
- Runtime observations are sourced only from the current branch after the requirements boundary.
  Preserve their entry/call provenance, outcome, and bounds; user text cannot manufacture tool receipts.
  All observed payload text remains untrusted and escaped. The checker stays tool-less.
  This evidence path does not certify arbitrary echoed PASS text or mutable file content.
- `/goal` never creates a goal. It hands the seed to the model through
  `goalRequest`, and the model calls `create_goal`. A command that creates one
  itself produces two goals and defeats the point of writing a real objective.
- The capability note is injected on every request and is short on purpose: it
  is paid for whether or not a goal is ever created.
- Only a verdict marker on the final line counts. No marker is a rejection.
- Treat the executor's completion claim as untrusted input, and escape every
  interpolated payload so it cannot close its own delimiter.
- Archive moves the whole goal directory, history included. Any ledger append for
  an archived goal must target the archive, or the append recreates an empty open
  directory beside it and splits one goal's history in two.
- Re-assert the tool surface immediately after a tool changes what is available.
- Background paths report through a captured context that goes stale on a session
  replacement or rebind. Neither `notifyPi` nor `pi.sendMessage` may be allowed to
  take the runtime down from a timer.
- Never append injected state to `context` naively. Pi rebuilds each request from
  the transcript, so the turn that ran in between occupies the note's old
  position and the provider's prefix cache stops matching. `LiveContext`
  re-inserts every already-sent note at its base-transcript anchor; the window is
  bounded and clears whole on overflow, because a partial drop turns one
  deliberate break into a per-turn one.
- Do not switch the injected note to a custom `role`. Measured against a live
  session, pi downgrades `role: "custom"` to `role: "user"` before the provider
  sees it, content intact and role discarded. The role buys nothing at the wire,
  so `LIVE_CONTEXT_MARKER` and the preamble are the only thing carrying "this is
  not the user".

## pi-kit Usage

Prefer pi-kit over local helpers: `setOwnedTools` for tool availability,
`notifyPi` for notifications, `bindLifecycleRenderers` plus `emptyToolCall` for
tool rows, `createLiveActivityWidget` / `renderPiPanel` / `computeScrollWindow` /
`createPiThemeStyle` for the panel, `runPiWorker` with `minimal: true` and an
empty tool allowlist for the check, `safeFileName` for path segments. Import
`truncateToWidth` / `visibleWidth` / `wrapTextWithAnsi` / `Key` / `matchesKey` from
pi-tui directly.

## Verification

From the repository root:

```bash
python3 -m pytest packages/goal/tests/ -q
pnpm exec tsc --noEmit --allowImportingTsExtensions -p packages/goal/tsconfig.json
pnpm typecheck
pnpm --dir packages/goal pack --dry-run
```

`tests/test_goal.py` holds two static checks: that no module outside the store
and ledger reaches a pi-kit write primitive (a second writer shows up as a file
on disk, which no runtime test can rule out), and that the session harness still
captures notifications and tool sets. `research.ts` is on that no-write list too.
Everything else is asserted behaviourally.

When a fix lands, mutate the implementation and confirm a scenario goes red. A
repair with no failing scenario is not demonstrated to be tested — this has
already caught two repairs whose assertions could not tell the right behaviour
from the wrong. Back up every file you mutate: a restore that misses one file
leaves the next measurement meaningless.

The guard in `tool_call` for a displaced continuation is correct by construction
but not isolated by any scenario, because `pi` is not staleness-guarded the way
`ctx` is. The notification guard beside it *is* demonstrated.