# @fradser/pi-agent-teams

Agent Teams combines subagent execution, the task set, and point-to-point messages.
The five intent tools are the only child tool surface:

```ts
agent_start({ identity: "reviewer", prompt: "Audit authentication" });
agent_input({ session: "session:reviewer:<incarnation>", prompt: "Review the correction", delivery: "next" });
agent_input({ session: "session:reviewer:<incarnation>", prompt: "Keep this read-only", delivery: "steer" });
agent_inspect({ session: "session:reviewer:<incarnation>" });
agent_list({});
agent_stop({ session: "session:reviewer:<incarnation>" });
```

Next input has a bounded FIFO queue and rechecks the original host's task policy.
A label changes display only; an identity selects saved instructions and private data.
Read [the intent contract](../subagents/README.md#intent-tools) for results, cancellation, and compatibility.
The `/agent-teams` console remains available.

## The retired `agent` tool

The `agent` tool and its six actions are gone, and no compatibility adapter
remains. A recorded branch that named `agent` receives the intent family on its
next session start. No user data moves. Read
[ADR-0008](../../docs/adr/0008-retire-the-legacy-agent-tool.md) for the decision.

An unknown role takes a compact inline definition:

```ts
agent_start({ label: "reader", prompt: "Read README.md and cite its install command",
  description: "Read evidence", role_prompt: "Read the assigned file and cite evidence", tools: ["read"] })
```

Only a user-authored disk `agent.md` declares durable identity. Disk definitions
always outrank inline input; invocation tools may narrow their grant, never widen it.
There are no persistence, Memory opt-in, worktree or promotion parameters. Choose minimal
canonical tool IDs (`read`, `bash`, `edit`, `write`, `grep`, `find`, `ls`,
`powershell`); extension aliases such as `ffgrep` are not inherited. Omitted
`tools` or `tools: []` grants only `message` and `task` for temporary team children,
never default shell or file access. Disk identities also receive `agent_memory`.
Start receipts and inspection expose the recorded effective grant, with a
coordination-only warning when applicable.
Inspection uses the session's recorded grant, not a changed role definition;
a record without a grant leaves it unknown rather than claiming no tools.

`agent_start` always takes a prompt and awaits the correlated
native input acknowledgement, not merely a writable pipe. It never creates an idle
child. Rejected, handled, timed-out or closed input never reports acceptance.
A receipt is not a result.

Every temporary or durable child remains **IDLE after a settled result** and accepts
next input in that exact incarnation. Steer guides active work; `agent_stop` and
parent shutdown close it. Later tasks notices can wake an idle team participant.
No child survives the parent Pi process. Hosted next input awaits native input acceptance
in the same process and history, publishing a new attempt before a later independent
input. Hosted steer awaits native steering acceptance without changing the
current sequence or attempt. An uncertain acknowledgement retains authority: inspect
or stop before retrying, rather than submitting competing input.

Canonical definitions are `<agent-dir>/agents/<name>/agent.md`,
`<project>/.pi/agents/<name>/agent.md`, and
`<project>/.pi/agents/<name>.local/agent.md`; precedence is project-local > project >
user > session. Every disk scope receives private Memory, an ordinary scratch directory
and project history at `<agent-dir>/agents/<name>/projects/<slug>/session/`.
Project overrides do not create a user-scope definition. Temporary roles use the
original project cwd with no-session and no private data. Durable children also launch
in the original project; scratch is data, not a checkout:
project edits change the original working tree directly. There is no Git isolation,
branch, automatic commit, merge or write confinement.

Identity, data provisioning and offline list entries belong to
[@fradser/pi-subagents](../subagents/VISION.md); team coordination does not create,
promote or clear that package's role registry.

`task` is activated only in valid assignment/tasks contexts and owns create/list/
update/complete/reopen. A Task describes what must be done, not who must do it;
participants take available Tasks with `update status=in_progress`.

Failed, interrupted, or crash-released Work returns to the tasks as
`pending/recovery-required`: the evidence stays available for inspection, and the
harness deliberately excludes it from autonomous notices. A participant must
proceed with a stated recovery reason, so a transient failure is never silently
retried. A retained superseded holder keeps `task` disclosed for exactly one failed
cancellation acknowledgement.

```ts
task({ action: "create", subject: "Fix storage", resources: ["firmware/storage"] })
task({ action: "update", id: "fix-storage", status: "in_progress" })
task({ action: "complete", id: "fix-storage", outcome: "success", result: "Verification evidence" })
```

`message` is communication-only. It accepts a body, a recipient or bound
reply route, and optional `inform`/`request` kind. Work lifecycle authority is
never inferred from message text.

```ts
message({ to: "session:reviewer:spawn-...", body: "The policy changed", kind: "inform" })
```

Automatic final answers (including autonomously claimed Work) and explicit Work
submission use the same attempt-bound acceptance pipeline. Explicit submission
ends the worker turn without a second automatic submission. Successful results
reach the Leader once, after execution settles and any verification gate passes.
Execution failures are reported after settlement without claiming acceptance.
`task list` includes bounded result evidence for deliberate recovery.
Verification freezes execution and retains deferred mail as Work history.
An ordinary final answer is a successful candidate, not independent verification;
ungated acceptance does not independently verify its claims. If requested work
cannot be performed, including missing tools, workers must explicitly submit
`task({ action: "complete", outcome: "failed", result: "Blocker and unverified work" })`.
Blocker prose is not classified as failure. Failed submission produces one failed
report, not completion or dependent unlock; a rejecting verification gate also
prevents acceptance. Leaders should delegate concrete acceptance criteria and an
explicit verification gate where appropriate. Informational reports need no
acknowledgment unless a decision or action changes.
Do not narrate repeated reports. This guidance does not suppress event transport
or infer lifecycle changes from communication.

A clean process exit while the resident is idle and owes no result stays in the console mailbox.
It records the stopped state and confirmed stop time without an unexpected-stop notification or another leader turn.
Unread mail addressed to the current incarnation prevents passive closure, even before inbox routing.
Malformed or incomplete unread records also prevent passive closure. Valid JSON alone does not prove that a message is valid.
The close check changes no inbox bytes, offsets, or delivery records. Stale or already-delivered messages do not create a new alarm.
Process failures, interrupted assignments, and unresolved results still reach the leader. Accepted results remain available after closure.

After delegation, continue independent work or end the turn: results resume the
session automatically. Use `agent_inspect` for deliberate diagnosis, not repeated
polling or sleep loops. `message` never creates or retries Work; messaging a
completed assignment returns its recorded result without waking the worker.
Worker communication and submissions are bound to the Assignment Attempt that
started the turn, so an old turn cannot report or submit as replacement Work, and
nonterminal coordination from a retired attempt stays in session history as
evidence without acting as a current instruction.
Recovery reuses the existing Task ID. A message does not release authority: wait
for the attempt to end or stop its stale exact session before taking the Task with
a stated recovery reason. Do not create competing recovery work through another startup. Read-only/no-write messages are steering, not cancellation or
proof that the current tool batch stopped. Native steering takes effect at safe
tool boundaries, before peer follow-up; it cannot undo already executed writes.
Parked verification requires explicit Task recovery; ordinary
messages remain deferred. Exact session handles are incarnation-bound, so a stale
handle cannot stop or inspect a replacement resident. Work persists for later inspection,
but a different session file does not import another session's tasks automatically.

## Coordination and delivery

Leader guidance uses the same delivery contract before and after a team starts:

- Delegate separable work with a task-scoped baseline, acceptance criteria and safe local checks. Use `task create` with `dependsOn` for prerequisites and shared `resources` tags for conflicting writes; participants take eligible Tasks. Independent delegation is not a substitute for dependencies.
- Implementers own assigned local checks. One integration owner checks shared behavior against the integrated candidate. Determine isolation needs before verification; commands running locally may still access user data or production credentials.
- Record a revision or scoped snapshot for the candidate and exclude unrelated dirty changes. Review and integration checks judge that same candidate; later edits invalidate affected evidence rather than automatically requiring every Agent to rerun every suite.
- A completed review Work Item can report REWORK. It is not a PASS on the implementation. Review-only work ends with that report, without editing the implementation or waiting for repairs; the implementation owner owns remediation. Implementation delivery stays pending until required Work and blocking reviews have returned, findings are resolved, and applicable evidence matches the final candidate. If only results remain outstanding, yield without announcing completion.
- Group related findings by root cause. Before a bounded recheck, preserve the prior report outside the result that reopen clears, and prepare the retained baseline, new candidate fingerprint, correction delta, prior findings and safe checks. If the description already references an authoritative current-attempt brief, update that brief before reopening and assigning, then keep it stable. Reopen/assign and the reopen reason do not change the old description or forward prior findings. A fixed conflicting description needs bounded follow-up Work with a refreshed description and `dependsOn` on the completed review. Messages to a closed assignment do not restart it; use a new broad review only when scope or risk changes.

`verify` is an independent reviewer's acceptance prompt, **not a shell command**. It adds a model-based acceptance gate when appropriate; it does not replace tests or make ungated reports independently verified. The contract above is prompt guidance, not a new scheduler, automatic snapshot system, or cross-extension completion lock.

Read [the role reference](references/agent-roles.md#assignment-brief) when preparing an assignment brief.

## Child environment

A spawned Agent receives an explicit non-secret environment, never the leader's
complete one. The allowlist covers runtime and locale, editor and pager, Git and
`SSH_AUTH_SOCK`, proxy and trust anchors, Node and language toolchain locations,
and the Pi process markers and configuration. `PI_CODING_AGENT_DIR` passes
through so the child resolves the same `auth.json` and `models.json` as the
leader; that is where Pi keeps OAuth credentials and literal `apiKey` values, so
a child needs the config directory rather than the parent's credential set.

Add an exact name to `PI_TEAMMATE_ENV_ALLOW` (comma-separated) when a provider
resolves credentials through environment interpolation:

```bash
export PI_TEAMMATE_ENV_ALLOW="MY_PROVIDER_API_KEY,AWS_PROFILE"
```

Opting in a credential-shaped name works and is reported, so a widening stays
visible. The allowlist variable itself does not travel to the child, so a nested
spawn reaches its own strict default. Spawn bindings the harness supplies always
win over both the allowlist and the leader environment.

The withheld count, the credential-shaped names, and the recovery instruction
appear in the `/agent-teams` detail view. That stays passive console telemetry
and never wakes the leader. Names embedding a private URL — npm's
`npm_config_//registry.example.com/:_authToken` shape — are redacted to a
recognizable prefix, and no withheld value is ever rendered.

This is leakage defense, not containment. A child granted `bash` can still read
`~/.pi/agent/auth.json`, `~/.aws/credentials`, or a project `.env` from disk;
kernel write and read confinement is a separate layer that does not exist yet.

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
