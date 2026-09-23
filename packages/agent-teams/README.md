# @fradser/pi-agent-teams

Agent Teams provides one final coordination surface for Pi:

```text
agent
work
agent_event
/agent-teams
```

`agent` manages Agent sessions through strict actions:

```ts
agent({ action: "delegate", name: "reviewer", prompt: "Audit authentication" })
agent({ action: "start", name: "reviewer" })
agent({ action: "inspect", name: "reviewer", session: "session:reviewer-...:spawn-..." })
agent({ action: "stop", session: "session:reviewer-...:spawn-..." })
```

A delegate action can include an inline definition. It is session-local unless
`persist: true` is explicitly supplied in that definition. Choose explicit minimal
canonical tool IDs (`read`, `bash`, `edit`, `write`, `grep`, `find`, `ls`,
`powershell`); extension aliases such as `ffgrep` are not inherited. Omitted
`tools` or `tools: []` grants only `agent_event` and `work`, never default shell
or file access. Delegate/start results and inspection expose the recorded
`session.tools` grant, with a coordination-only warning when applicable.
Inspection uses the session's recorded grant, not a changed role definition;
legacy records without a grant leave it unknown rather than claiming no tools.

For an unknown role, provide a compact inline definition:

```ts
agent({ action: "delegate", name: "reader", prompt: "Read README.md and cite its install command",
  definition: { description: "Read evidence", prompt: "Read the assigned file and cite evidence", tools: ["read"] } })
```

`agent start` creates an unassigned resident without a synthetic Work ID or an
initial model turn. Presence stays `starting` until a one-shot native readiness
acknowledgement, then becomes `idle` and eligible for exact-session assignment.
The public start call awaits that bounded acknowledgement before returning, so
its exact returned session accepts an immediate assignment without a caller wait.
Rejected readiness, timeout, or early exit fails the start call; a process ID is
not readiness. Reassigning the same still-claimed Work to its exact current owner
returns the existing Assignment Attempt without a second delivery. Later claimable-board notices can still wake
the resident and activate deliberate autonomous claims. Start is not a permanent
assignment-only scheduling mode.

`work` is activated only in valid assignment/board contexts.

`work` owns Work lifecycle. Leaders create/list/assign/release/reopen completed
Work/supersede; Workers list/claim/submit/release their current Work.

Failed, interrupted, or crash-released Work returns to the board as
`pending/recovery-required`: the evidence stays available for inspection, and the
harness deliberately excludes it from autonomous claim notices. Only an explicit
leader `work assign` opens the next attempt, so a transient failure is never
silently retried by whichever resident happens to be idle. A retained superseded
holder keeps `work` disclosed for exactly one failed cancellation acknowledgement.

```ts
work({ action: "create", subject: "Fix storage", resources: ["firmware/storage"] })
work({ action: "assign", id: "fix-storage", target: { session: "session:worker-...:spawn-..." } })
work({ action: "claim" })
work({ action: "submit", outcome: "success", result: "Verification evidence" })
```

`agent_event` is communication-only. It accepts a message, a recipient or bound
reply route, and optional `inform`/`request` intent. Work lifecycle authority is
never inferred from message text.

```ts
agent_event({ to: "session:reviewer-...:spawn-...", message: "The policy changed", intent: "inform" })
```

Automatic final answers (including autonomously claimed Work) and explicit Work
submission use the same attempt-bound acceptance pipeline. Explicit submission
ends the worker turn without a second automatic submission. Successful results
reach the Leader once, after execution settles and any verification gate passes.
Execution failures are reported after settlement without claiming acceptance.
`work list` includes bounded result evidence for deliberate recovery.
Verification freezes execution and retains deferred mail as Work history.
An ordinary final answer is a successful candidate, not independent verification;
ungated acceptance does not independently verify its claims. If requested work
cannot be performed, including missing tools, workers must explicitly submit
`work({ action: "submit", outcome: "failed", result: "Blocker and unverified work" })`.
Blocker prose is not classified as failure. Failed submission produces one failed
report, not completion or dependent unlock; a rejecting verification gate also
prevents acceptance. Leaders should delegate concrete acceptance criteria and an
explicit verification gate where appropriate. Informational reports need no
acknowledgment unless a decision or action changes.
Do not narrate repeated reports. This guidance does not suppress event transport
or infer lifecycle changes from communication.

After delegation, continue independent work or end the turn: results resume the
session automatically. Use `agent inspect` for deliberate diagnosis, not repeated
polling or sleep loops. `agent_event` never creates or retries Work; messaging a
completed assignment returns its recorded result without waking the worker.
Worker communication and submissions are bound to the Assignment Attempt that
started the turn, so an old turn cannot report or submit as replacement Work, and
nonterminal coordination from a retired attempt stays in session history as
evidence without acting as a current instruction.
Recovery reuses the existing Work ID. Request explicit `work release` and await
authoritative release before `work assign` to the chosen exact session; a queued
release is not yet released authority. Do not create competing recovery Work via
`agent delegate`. Read-only/no-write messages are steering, not cancellation or
proof that the current tool batch stopped. Native steering takes effect at safe
tool boundaries, before peer follow-up; it cannot undo already executed writes.
Parked verification requires explicit Work release and reassignment; ordinary
messages remain deferred. Exact session handles are incarnation-bound, so a stale
handle cannot stop or inspect a replacement resident. Work persists for later inspection,
but a different session file does not import another session's tasks automatically.

## Coordination and delivery

Leader guidance uses the same delivery contract before and after a team starts:

- Delegate separable work with a task-scoped baseline, acceptance criteria and safe local checks. Use `work create` with `dependsOn` for prerequisites and shared `resources` tags for conflicting writes; then assign eligible Work. Independent delegation is not a substitute for dependencies.
- Implementers own assigned local checks. One integration owner checks shared behavior against the integrated candidate. Determine isolation needs before verification; commands running locally may still access user data or production credentials.
- Record a revision or scoped snapshot for the candidate and exclude unrelated dirty changes. Review and integration checks judge that same candidate; later edits invalidate affected evidence rather than automatically requiring every Agent to rerun every suite.
- A completed review Work Item can report REWORK. It is not a PASS on the implementation. Review-only work ends with that report, without editing the implementation or waiting for repairs; the implementation owner owns remediation. Implementation delivery stays pending until required Work and blocking reviews have returned, findings are resolved, and applicable evidence matches the final candidate. If only results remain outstanding, yield without announcing completion.
- Group related findings by root cause. Before a bounded recheck, preserve the prior report outside the result that reopen clears, and prepare the retained baseline, new candidate fingerprint, correction delta, prior findings and safe checks. If the description already references an authoritative current-attempt brief, update that brief before reopening and assigning, then keep it stable. Reopen/assign and the reopen reason do not change the old description or forward prior findings. A fixed conflicting description needs bounded follow-up Work with a refreshed description and `dependsOn` on the completed review. Messages to a closed assignment do not restart it; use a new broad review only when scope or risk changes.

`verify` is an independent reviewer's acceptance prompt, **not a shell command**. It adds a model-based acceptance gate when appropriate; it does not replace tests or make ungated reports independently verified. The contract above is prompt guidance, not a new scheduler, automatic snapshot system, or cross-extension completion lock.

Read [the role reference](references/agent-roles.md#assignment-brief) when preparing an assignment brief.

## Message display

Collapsed `[message]` rows use the current terminal width for their preview and
reserve the complete configured expansion-key hint. Expanded rows show the full
message once, inline after the recipient and delivery state, with natural wrapping
and preserved line breaks. Literal JSON quotes and punctuation spacing remain
unchanged; message content bypasses prose cleanup. Routing identifiers remain
model-facing, not transcript copy; real extra notes are separate from the message
and are not repeated previews.
The renderer uses the same pi-kit lifecycle abstraction as `[context] researched`;
only the content model differs: research has a distinct query and answer, while a
sent message expands its inline text.

## Install

```bash
pi install npm:@fradser/pi-agent-teams
```

Run `/reload` after installation. `/agent-teams` is the human management
surface for Presence, Work, diagnostics, and exact-session stop controls.

## License

MIT
