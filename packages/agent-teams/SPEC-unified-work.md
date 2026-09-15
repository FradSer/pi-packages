# Agent Teams: retain advanced Work, remove duplicate coordination paths

Status: ready-for-agent specification; planning complete, not implemented.
Tracker: package-local specification, as confirmed by the user. No remote issues or new tracker setup.
Execution plan: @PLAN-unified-work.md. Acceptance contract: @features/unified-work-interface.feature.
Planning review: independent read-only re-audit returned PASS on 2026-09-15 with no remaining policy blockers. Runtime acceptance still requires proof that the resident adapter prevents already-queued Pi turns from executing during verification; planning approval is not implementation verification.

## Problem Statement

The Leader currently chooses between overlapping startup, messaging, inspection, and completion operations. Ordinary delegation and the task board enforce similar ownership rules through different records and result paths. The latest anti-polling patch adds repeated advice to tool descriptions and results without reducing those choices.

The user wants less redundancy while retaining advanced Work management, resident execution, autonomous claiming, dependencies, resources, verification, and recovery. Removing those capabilities to obtain two tool names is not the chosen direction.

## Solution

Expose three coordination tools with distinct responsibilities:

- **agent** manages Agent definitions and resident execution; its delegate operation creates and assigns a normal Work Item in one call.
- **work** manages the single Work Item lifecycle, including explicit creation, assignment, claiming, submission, reopening, release, and supersession.
- **agent_event** carries messages between participants. It cannot submit, complete, reopen, or transfer work authority.

The board becomes a view of pending Work Items, not a second work model. Ordinary final answers and explicit submissions enter the same acceptance pipeline. The Team Console remains the human management surface; deliberate inspection remains available without becoming a waiting protocol.

### Confirmed product choices

1. Keep one-call agent delegation alongside advanced Work control; both use the same Work Item.
2. Automatically submit an ordinary final answer and allow explicit work submit. Both use the same verification policy and deduplication.
3. Keep unassigned residents and autonomous claim after actionable board notices.
4. Consolidate to three tool names, replacing old coordination tools rather than adding aliases.
5. Produce a package-local specification and implementation plan only in this task.
6. Freeze owner execution during verification and while parked; retain mail without waking the owner. A first failed review may authorize a revision; PASS archives the deferred mail with a result reference.
7. Superseded-owner release acknowledges revocation without resurrecting work. Reopening a settled parked holding atomically retires its authority. Confirmed requested stop fails unfinished work unless an earlier release intent makes it pending; superseded and completed work keep their states.
8. Reject reopening a prerequisite while any direct or indirect dependent is active, verifying, parked, or retaining revoked authority. Do not introduce dependency-acceptance versions in this slice.

The detailed operation and state rules below implement those choices in the proposed design. They are not claims about the installed extension.

## User Stories

1. As a Leader, I want to delegate once to a defined Agent so that a complete Work Item starts without process bookkeeping.
2. As a Leader, I want to supply an explicit temporary definition in that same call so that a new role does not require another startup tool.
3. As a user, I want generated definitions to remain session-local unless I request persistence so that a one-off assignment does not alter my role library.
4. As a Leader, I want concurrent delegations to one Agent to remain independent so that one prompt cannot silently steer another assignment.
5. As a Leader, I want fresh context by default and an explicit fork option so that independent judgment and context inheritance remain deliberate.
6. As a Leader, I want to start an unassigned resident so that it can later claim suitable Work Items without inventing a pending result.
7. As a Leader, I want to create unassigned work with dependencies, resources, and verification so that advanced scheduling remains available.
8. As a Leader, I want to assign existing work to an exact idle session or fresh Agent execution so that scheduling does not create duplicate Work Items.
9. As a Worker, I want to claim eligible work after a board notice so that residents can self-organize without Leader polling.
10. As a Worker, I want an authoritative claim acceptance so that I cannot start work merely because my request was queued.
11. As a maintainer, I want one ownership and resource guard for all Work Items so that entry-point choice cannot bypass concurrency safety.
12. As a Worker, I want my ordinary final answer to submit work automatically so that routine completion needs no bookkeeping call.
13. As a Worker, I want explicit submission to use the same acceptance pipeline so that advanced execution does not bypass verification or report twice.
14. As a Leader, I want verification-pending work distinguished from accepted work so that dependents never run on an unverified result.
15. As a Worker, I want failed review findings returned to my current holding so that I can fix and resubmit without losing resource authority.
16. As a Leader, I want repeated or inconclusive verification to request one decision so that a resident cannot loop indefinitely or claim a false PASS.
17. As a Leader, I want to reopen failed or completed work explicitly so that a previous result cannot complete a new Assignment Attempt.
18. As a Leader, I want to release or supersede work safely so that cancellation cannot unlock resources while an old Worker still writes.
19. As a participant, I want one message operation with precise routing so that new evidence reaches the intended Work Session without changing ownership.
20. As a user, I want bounded Presence and Work projections so that deliberate diagnosis does not require raw transport details or report resends.
21. As a Leader, I want stopping a process distinguished from successful work so that cleanup is not mistaken for completion.
22. As a maintainer, I want one public test seam and one lifecycle implementation so that internal refactors do not require editing repeated prose assertions.
23. As a Leader, I want verification to exclude same-owner execution so that a PASS describes the submitted work rather than files changed during review.
24. As a Leader, I want each recovery operation to have a defined state and resource outcome so that cleanup cannot resurrect obsolete work or strand a parked holding.
25. As a Leader, I want reopening a prerequisite to check active dependents atomically so that running work cannot lose the prerequisite acceptance that authorized it.

## Scenarios

The Gherkin contract at @features/unified-work-interface.feature covers the confirmed choices and engineering proposal. It is tagged as unimplemented until its public-seam tests drive each delivery slice. It does not replace the current runtime scenarios during this planning task.

## Implementation Decisions

### Three interfaces, not three bags of optional parameters

Each action has a discriminated schema with only its relevant fields. Intent is explicit; omitting a prompt no longer switches a delegation call into inspection or resident startup. Invalid action/field combinations fail before side effects.

| Tool | Operations | Responsibility |
|---|---|---|
| agent | delegate, start, inspect, stop | Define roles inline, start fresh delegated work or an unassigned resident, read Presence, stop exact execution |
| work | create, list, assign, claim, submit, reopen, release, supersede | Own work authorization, scheduling, submission, acceptance, and recovery |
| agent_event | send information or a request | Route messages without lifecycle authority |

Definition registration is part of start/delegate, not another tool. Existing definition precedence and explicit persistence rules remain. An unknown name without a valid inline definition fails; the runtime does not guess capabilities. Fork and model override apply only when creating execution. Fork requires an available context snapshot and preserves the current parent-isolation guarantees.

Agent delegate is a convenience operation over the same create-and-assign transition used by Work control, not another implementation of it. It accepts resource and verification requirements, returns the normal Work handle, and always starts independent execution. It has no existing-work steering or implicit reopen branch. A resource or validation rejection leaves no partial creation; a launch failure after authorization records a failed attempt and a visible recoverable Work Item.

### Role-scoped Work control

- The Leader can create, list, assign, reopen, release, and supersede work. It cannot impersonate a Worker submission or claim.
- An idle resident may list and claim only after eligible work is offered. One Work Session can own at most one current Assignment Attempt.
- A current owner may submit or voluntarily release its work. Sender and attempt bindings are runtime-owned, not caller-provided credentials.
- Assignment to an existing session requires a precise, idle, live target. Assignment to an Agent creates fresh execution. Target kinds are explicit; the runtime does not silently choose among concurrent sessions.
- Create records pending work without spawning. Claim writes an intent; only the single writer's accepted binding authorizes execution. Assign and claim use the same ownership guard and require current acceptance of direct and indirect prerequisites.
- List supports bounded filtering and reading one known Work Item, including its accepted result and attempt history. It is a state query, not a completion subscription.
- Reopen, release, supersede, and session stop use the recovery table below. They never derive authority from ordinary mail or a result's prose.
- Supersede atomically creates the replacement and rewrites pending dependency edges. Cycles, missing references, and superseding accepted work are rejected. Resource retirement follows the recovery table, not the dependency rewrite.

### Recovery transitions

All rows are single-writer decisions against the current holding and submission. Safe retirement means authoring execution is settled and frozen with no queued turn able to start, or process stop is confirmed. A bound owner release ends its execution sequence; its queued intent alone is not proof that writes have stopped.

| Operation and eligible source | Synchronous transition | State after safe retirement |
|---|---|---|
| Reopen completed, failed, or verification-parked work | Require safe retirement and the dependent guard below; atomically invalidate acceptance, old submission/gate authority, and any parked holding; release its resources | pending, no owner; no separate release call and no new process |
| Leader release active, verifying, or failed work | Invalidate pending acceptance and gate authority; freeze ordinary mail. If authoring still runs, retain the holding with release intent until bound owner acknowledgement plus settlement, or confirmed stop | pending, no owner |
| Bound owner release active work | Record release intent and end the authoring sequence; invalidate pending submission authority | pending once settled, no owner |
| Release a superseded holding, including its bound owner's acknowledgement | Preserve superseded state and replacement reference; retire only the matching old authority when safe | superseded, no owner; never pending or completed |
| Supersede unfinished work | Mark superseded, invalidate its pending submission/gate authority, and record revocation. Retain resources while the old owner can still write | superseded after acknowledgement plus settlement or confirmed stop |
| Standalone requested stop of an active/verifying owner | Mark stop intent, block acceptance and further execution dispatch, invalidate the current gate; retain ownership until stop confirmation | failed with a stopped reason, no owner |
| Stop of an owner with an already accepted release intent | Keep that release intent; stop confirmation provides its safe-retirement evidence | pending, no owner |
| Stop of a superseded holder, completed-work resident, or unassigned resident | Preserve the Work state; stop exact execution only | superseded stays superseded, completed stays completed; no Work Item is fabricated |

A confirmed stop of an already failed holding leaves it failed unless an earlier release intent applies. Reopen is rejected for active work, a live non-parked review, or unresolved revocation; it does not first issue a stop or release. Leader release of pending or completed work is rejected; completed work must be explicitly reopened. Once a standalone stop intent is accepted, a later release or reopen is rejected until stop confirmation; it cannot change the pending stop's failed outcome into an implicit retry. Superseded work cannot be reopened or reassigned. A parked owner is already settled and frozen, so a Leader release or reopen can retire it directly without waking it to manufacture an acknowledgement.

A pending release or stop blocks submissions and reviewer acceptance even if physical termination is not yet confirmed. Cancellation feedback and bound release acknowledgements are lifecycle control, not ordinary mail; they can close a running holding while new ordinary execution stays blocked. If PASS is applied first, a later stop leaves completed work completed. If stop/release/supersession is accepted first, a later PASS is stale. Superseded state takes precedence over pending cleanup intents. Stop failure leaves its intent, owner, and resources visible for explicit recovery; it does not make the Work Item claimable. Owner replies, stop callbacks, and duplicate acknowledgements are correlated to the exact retired holding and cannot affect a replacement.

### Prerequisite reopening

Before reopening a Work Item, traverse its direct and indirect dependents. Reject with the blocking Work IDs if any dependent is active, verifying (including parked), or retaining an execution/resource holding during revocation. Failed or superseded dependents whose authority is safely retired do not block. Already completed dependents stay completed as historical accepted results. Acquisition of unstarted work traverses all direct and indirect prerequisites and requires their current acceptance; completed intermediate nodes do not bypass a reopened ancestor. Thus for A -> B -> C with B completed and C pending, reopening A preserves B's history but blocks C until A is accepted again.

This check and acceptance invalidation form one atomic ledger transition shared with assign and claim. If a dependent acquires first, reopen rejects. If reopen succeeds first, dependent acquisition sees the unmet prerequisite and rejects. The runtime does not cancel dependents implicitly or pin them to old prerequisite versions. The Leader must safely finish or release blocking work before retrying reopen.

### One work lifecycle

The lifecycle projection is pending, active, verifying, completed, failed, or superseded. Dependency/resource blockers and verification attention are reasons attached to those states, not additional parallel status machines. Revocation is pending intent while a live holder retains authority.

A Work Item owns its stable ID, requirements, dependencies, resource tags, effective verification policy, and accepted-result reference. An Assignment Attempt identifies the current owner and execution authority. A submission identifies one candidate result within that holding; failed review may produce another submission without releasing it. Process liveness and Work acceptance remain separate.

All acquisition paths use the same transitions. The old direct-versus-board kind is removed as an authority switch. After accepted completion, an eligible resident may receive later claimable-work notices regardless of how it acquired the previous Work Item. New one-call delegations still start independent Work Sessions rather than opportunistically reusing residents.

Without a previously accepted release or supersession intent, runtime failure or a failed submission produces failed work, blocks dependents, and emits one failure outcome. If cleanup intent is already pending, the recovery table determines the outcome instead; an old owner's failure cannot overwrite superseded state or an accepted release. It does not silently requeue board work while treating direct work differently. Explicit reopen or release makes retry policy visible. Spawn/attempt identity, replay suppression, safe stop, resource conflict, and supersession invariants remain enforced.

### Submission is not acceptance

The settled ordinary final answer and explicit work submit produce the same internal submission event. Explicit submission ends the Worker turn and suppresses automatic duplication for that submission cycle. Neither execution ending nor a result's prose bypasses verification.

The effective gate is Work-specific verification when supplied, otherwise the assigned Agent's default, pinned for the holding. Gate evaluation waits for authoring settlement and the execution freeze below. With no gate the result is accepted at settlement; with a gate the Work Item remains verifying and retains resources until PASS. Only acceptance completes work and unlocks dependent work.

Retain the existing review policy: first FAIL returns findings to the same owner; a second consecutive FAIL parks the holding and notifies the Leader once. Missing verdict receives one clarification, then parks as inconclusive rather than counting as a defect or success. Explicit Work control resolves a parked holding; more ordinary mail cannot implicitly reset its retry budget. Reopen followed by assign/claim starts a new attempt; release deliberately makes unfinished work available again.

Each submission and reviewer result is correlated to the Work Item, Assignment Attempt, submission identity, and current review authorization. A delayed gate, repeat settlement, or old report cannot accept, close, or unlock a newer attempt or revision. Retain bounded large-result retrieval. Accepted and failed Work outcomes use one automatic result channel with attempt evidence; ordinary messages never duplicate completion announcements.

### Execution freeze during verification

Submission closes execution-producing mail dispatch before review starts. The runtime holds Leader steering, peer follow-ups, and already-queued execution for that Work Session; verification cannot overlap another authoring turn. An in-flight tool is not declared stopped merely by changing a ledger flag. Review begins only when authoring has settled and queued input cannot start another turn. Enforce this at the resident execution/dispatch seam as well as at message receipt. If quiescence cannot be established, leave acceptance pending with an actionable reason. This is a guarantee about runtime-controlled execution, not a sandbox guarantee against arbitrary external writers or detached commands.

While verifying or parked, incoming ordinary messages remain in a bounded deferred queue correlated to the addressed attempt and do not wake any owner turn, even a supposedly read-only one. Successful receipt reports deferred routing, not consumption. Full-queue failure is explicit; no accepted mail is silently dropped.

- First FAIL: retire the old review authorization and authorize a revision before resuming the same owner. Deliver findings and still-applicable deferred mail through that revision; a later PASS for the old submission is invalid.
- PASS: accept the current submission, retire execution authority, and retain deferred mail as historical evidence linked from the Work result. It does not run after completion or flow into the resident's next assignment. The Leader can read it and explicitly reopen if it changes the conclusion.
- Repeated FAIL or inconclusive park: keep the owner frozen and its resources held. Mail neither starts a revision nor clears the attention reason. Recovery uses the table above.
- Release, reopen, supersede, or stop: invalidate the current review authorization before retirement; deferred mail remains bound to the old attempt as history.

If unexpected owner execution is observed during review, invalidate review authorization before any PASS can apply, keep the holding reserved, and raise one actionable attention event. Do not interpret that execution as an authorized revision or automatically resubmit. This is failure recovery, not a heartbeat notification.

### Messages and receipts

All participants use agent_event with message, optional recipient, and optional intent limited to inform/request. Intent labels content, not authorization. Lifecycle status, resource replacement, reopening, and handoff authority are Work operations, not message fields. Coordinated transfer remains release-and-assign; a new offer/accept handoff protocol is outside this slice.

A precise Work/session route binds to the current attempt at send time. If that attempt closes before consumption, the event is historical or rejected; it does not become guidance for the next attempt. A bare Agent name requires one unambiguous live recipient; omitted recipient requires one bound reply route. Preserve native Leader priority steering, lower-priority peer follow-up, abort propagation, and safe-boundary delivery when execution is authorized; the verification/revocation freeze overrides dispatch, not sender priority. No global durable Agent inbox or automatic wake-on-inform policy is introduced.

Receipts contain the authoritative scope, handles, state, synchronous outcome, and a concise pending next actor when needed. Queued intent is not applied state, and routed mail is not proof of consumption. Detailed transport telemetry remains available in diagnostics. One short positive Leader policy describes independent work/yield/result acceptance; startup and routing results do not each repeat a paragraph of anti-polling instructions. Deliberate inspection remains legal, so prompt wording cannot guarantee that a model will never poll.

### Locality and lifecycle storage

Keep one in-process Work lifecycle module and one submission pipeline, with the existing process, file, and Pi-kit facilities behind their internal seams. Tool registrations and the Team Console consume these operations instead of implementing their own transitions. This is not a mandate to create separate Directory, Lease, Memory, or Event-Store modules.

The current Leader runtime remains the single writer. Residents submit correlated intents; atomic local snapshots and existing session-scoped persistence are sufficient. Preserve resume of the same board scope and rejection of dead/stale ownership; do not import work from another Leader runtime. Incompatible old snapshots are reported explicitly, never silently discarded or translated through a permanent compatibility layer.

The public cutover removes teammate_spawn, teammate_shutdown, send_message, task_create, task_list, task_claim, and task_submit together with obsolete parameter schemas and guidance. Advanced operations are disclosed by role and valid state under work, not by restoring old tool names. Runtime validation remains authoritative even for forged or stale requests.

## Testing Decisions

- Primary seam: real registered coordination tools with real state reducers and temporary local storage; substitute the existing child-process transport seam and verification runner rather than mocking the lifecycle internals.
- Drive automatic submissions through actual Worker lifecycle hooks and scripted process events. Assert one authorized assignment, one accepted result, ordering, resource retention, and rejection of stale evidence.
- Reuse the established Python-to-Node harness, real SessionManager fork fixtures, claim races, verification races, stop confirmation, and late-report scenarios.
- Replace obsolete source-text and duplicate hint assertions as each behavior moves to the new seam. Test the observable contract, not exact advisory English or helper names.
- Begin each implementation slice with the relevant Gherkin scenario and a failing public-seam test. Do not mark these design scenarios implemented merely because a documentation check passes.
- Final acceptance includes package tests, root tests, typecheck, packed-manifest validation, installed-path validation, fresh-agent audit, and actual Pi print and interactive Team Console checks. Run heavy suites once, not concurrently against shared runtime state. External authentication or unrelated root failures must be reported separately.

## Out of Scope

Automatic role promotion or new Agent Memory; cross-runtime scheduling, a global persistent inbox or daemon; cloud-computer abstraction, Preview or Takeover; a new handoff-offer protocol; removal of resident/self-claim capability; removing intentional inspection; replacing Pi-kit or the established transport; compatibility aliases or legacy-state migration; implementation or release during this planning task.

## Further Notes

This supersedes the two-tool target and removal of model-facing board controls for the next coordination slice. It does not reverse the durable Agent identity direction or the no-heartbeat ADR. Prior specifications remain evidence for currently shipped behavior, especially fresh/fork context, precise routing, current single-writer scope, and automatic results; they are not authority for reintroducing duplicate paths in this slice.

The preceding anti-polling patch remains uncommitted implementation work in the repository. Do not discard it wholesale during planning or mix other sessions' changes into this effort. Its duplicated receipt helpers and wording-specific tests are explicit deletion targets at the final cutover, once the replacement seam has behavioral coverage.
