# Implementation plan: unified Work with resident scheduling

Status: ready for implementation; planning complete. Independent planning review is recorded in @SPEC-unified-work.md. No runtime cutover has been performed.
Product contract: @SPEC-unified-work.md.
BDD contract: @features/unified-work-interface.feature.

## Destination

Retain advanced scheduling while replacing overlapping tool families with agent, work, and agent_event. One-call delegation and board acquisition must share ownership, resource, submission, and verification behavior. A plan is not complete if it merely renames the current tools or hides two state machines under a large action switch.

## Interface sketch

These examples describe the proposed final interface, not tools currently installed in Pi. Action-specific TypeBox unions reject irrelevant fields. Keep the existing name/prompt/fork vocabulary where it still fits; remove absent-prompt overloads and implicit lifecycle changes.

### Agent operations

| Action | Required inputs | Optional inputs | Outcome |
|---|---|---|---|
| delegate | name, prompt | definition, resources, verify, fork, model | Create/assign one Work Item and start independent execution |
| start | name | definition, model | Start an unassigned resident and return its exact session handle |
| inspect | name | session | Read bounded Presence without execution |
| stop | session | — | Stop exact execution; unfinished work fails on confirmation unless an earlier release applies; never delete the Agent definition |

Inline definition retains description, tools, role prompt, and the existing role attributes. Generated roles are ephemeral by default; only explicit user authorization permits persistence. Starting a fresh unassigned resident has no fork because it has no assigned work to inherit context for.

```ts
agent({ action: "delegate", name: "reviewer", prompt: "Audit auth middleware" });
// -> work ID, attempt ID, session route, state

agent({ action: "start", name: "backend", definition: backendDefinition });
// -> idle-capable resident session; no Work Item or promised final result

agent({ action: "inspect", name: "reviewer" });
agent({ action: "stop", session: "<returned session>" });
```

### Work operations

| Action | Inputs | Authority and effect |
|---|---|---|
| create | subject; description?, dependsOn?, resources?, verify? | Leader; create pending work, notify eligible residents, never spawn |
| list | id? or bounded state/claimable filter and cursor | Leader view or eligible Worker view; include result and current holding when selecting one ID |
| assign | id, target | Leader; target is exactly one of Agent name for fresh execution or exact idle session |
| claim | id? | Eligible idle Worker; queue a claim intent and await authoritative acceptance |
| submit | result, outcome: success/failed | Current bound owner; candidate result, not acceptance; no caller-supplied owner or attempt |
| reopen | id, reason | Leader; atomically retire safely settled terminal/parked authority to pending; reject live dependent authority |
| release | reason; id for Leader, bound work for Worker | Relinquish unfinished/failed work to pending; superseded acknowledgement stays superseded; retain live locks until settlement/stop |
| supersede | ids, replacement work requirements | Leader; atomically create replacement and rewire pending dependencies |

A fresh-execution assign target may select fork/model; an existing-session target cannot change its context or model. Resource and verification requirements are owned by the Work Item, not copied into messaging calls. Reusing a resident is always explicit through assign or an accepted claim, never a side effect of delegate.

```ts
work({
  action: "create", subject: "Fix auth findings", description: "Implement the accepted review findings",
  dependsOn: ["<review work>"], resources: ["src/auth"], verify: "All auth acceptance scenarios hold",
});

work({ action: "assign", id: "<fix work>", target: { agent: "backend" } });
work({ action: "assign", id: "<other pending work>", target: { session: "<idle session>" } });

// Worker after an eligible board notice:
work({ action: "claim", id: "<offered work>" });
// Work begins only after the runtime binds the accepted claim.
work({ action: "submit", outcome: "success", result: "Implementation and verification evidence" });
// Ordinary final answers use this same submission path automatically.

work({ action: "reopen", id: "<failed work>", reason: "Dependency issue is resolved" });
work({ action: "assign", id: "<same work>", target: { agent: "backend" } });
```

### Shared communication

```ts
agent_event({ to: "<returned Work or session route>", message: "New evidence changes the second finding" });
agent_event({ message: "A decision is needed on the conflicting requirement", intent: "request" });
```

A missing recipient requires a unique bound reply route. Work routes are resolved and pinned to the current attempt at send time, not re-resolved onto a future attempt at delivery. Completion/failed status, resource changes, and reopen parameters are absent. No routing acknowledgement proves consumption.

These are three tool names but more than three operations. Keep schemas role-scoped, state-aware, and exhaustive; do not advertise the whole management surface to an executing Worker. The runtime must reject unauthorized operations even when the caller bypasses disclosure.

## Lifecycle rules to implement first

The authoritative transitions are in @SPEC-unified-work.md under “Recovery transitions”, “Prerequisite reopening”, and “Execution freeze during verification”. Implement them with the first affected lifecycle slice, not as final hardening.

The ordinary path is pending -> active -> verifying -> completed; ungated acceptance skips verifying. A first review failure authorizes a revision under the same holding, while repeated or inconclusive review stays frozen awaiting a decision. Failed execution does not automatically retry. Revocation retains authority until safe retirement rather than introducing another independent Work status.

Three race-sensitive rules are now confirmed:

1. **Freeze the owner during review and park.** Hold all execution-producing mail, including previously queued input, until a runtime-authorized revision. PASS accepts the unchanged submission and archives deferred mail with a result reference. Observed unexpected owner execution invalidates review authorization and requests attention; it cannot authorize its own revision.
2. **Resolve recovery atomically.** Superseded-owner release retires only old resources and preserves superseded state. Reopen retires a settled parked holding itself, without a preliminary release call. Requested stop blocks acceptance immediately and, once confirmed, preserves prior release/supersession/completion outcomes or fails other unfinished work.
3. **Guard prerequisite reopening against live dependents.** Direct and indirect active/verifying/parked dependents and revoked holders block reopen. The dependent check and invalidation share the assign/claim transaction, avoiding a check-then-start race. Unstarted work checks current prerequisite acceptance; completed downstream results remain historical.

These are runtime-controlled execution guarantees. Authoring settlement plus an ordinary state flag does not prove that queued Pi turns or arbitrary detached commands have stopped. The execution adapter must gate queued input before verification can start; inability to establish quiescence leaves acceptance pending.

## Current evidence and replacement targets

| Current seam or responsibility | Evidence | Planned treatment |
|---|---|---|
| Compact delegation and implicit steer/reopen | @src/agent-control.ts | Keep the one-call convenience, route it through unified create/assign, remove work/prompt overload |
| Leader registrations and dynamic tool names | @src/tools.ts | Replace old registrations; keep rendering/translation thin |
| Worker capabilities and automatic direct-only result | @src/worker.ts | Register role-scoped work operations; route all assigned finals and explicit submit through one pipeline |
| Direct assignment versus BoardTask | @src/types.ts and @src/state.ts | One Work record and attempt authority; eliminate kind-specific guards |
| Claims/submissions, verify, wake-up, stop | @src/team-machine.ts | Preserve proven invariants and transport; concentrate Work transitions instead of mirroring them |
| Single-writer persistence and intent files | @src/statefile.ts | Reuse local atomic writes; correlate claim/submission and acceptance without adding a new broker |
| Fork/context isolation | @src/work-context.ts and @SPEC-work-sessions.md | Preserve, not redesign |
| Role definitions and process transport | @src/agents.ts and @src/spawner.ts | Reuse existing resolution, tool grants, process lifetime, and abort behavior |
| Passive console and transcript | @src/ui.ts, @src/tool-render.ts, @src/leader-reports.ts | Project unified work state and automatic outcomes; keep diagnostics distinct from acceptance |
| Repeated anti-polling prose | @src/guidance.ts, @src/agent-control.ts, @src/tools.ts | Replace receipt-specific paragraphs with factual receipts and one short shared policy |

Dependency strategy: reducers and in-memory projections are in-process; temp filesystem and scripted resident RPC are local-substitutable; actual Pi/model execution is an external adapter. Use the existing testable process seam and verification runner. No new adapter hierarchy is justified merely by the prospective names in the older DESIGN.

## Delivery slices

Implement in this order. Every slice begins with its feature scenario and one RED public-seam test, then enough code for GREEN. Keep the product runnable; do not merge a scaffold with no end-to-end path.

### 1. One Work record behind both acquisition paths

- Start with one delegated Work Item appearing alongside created/claimed work in the same query projection.
- Centralize resource/dependency/one-owner checks and stable Work/attempt identity. Preserve exact-session routing and current runtime scoping.
- Migrate all current acquisition handlers onto that single implementation in the same slice. Do not introduce dual stores or a second reducer kept in sync.
- Implement the recovery table for all existing ownership paths now: safe release, superseded-owner acknowledgement, parked reopen retirement, and requested-stop outcome precedence. Invalidate pending acceptance as soon as revocation is accepted.
- Make prerequisite reopening and dependent acquisition one atomic decision, including indirect dependencies and retained revoked holdings.
- Test direct-versus-claimed resource conflicts, concurrent same-Agent delegation, claim races, stopped owners, atomic startup failures, supersession acknowledgement, and reopen/claim races.

**Exit:** current public operations still work, but changing ownership rules has one implementation and tests prove shared invariants. Old tool registrations are only consumers of the unified implementation while the cutover is prepared; no release of both public tool families.

### 2. One submission and verification pipeline

- Lift the direct-only settled-result hook to any current authorized holding.
- Route explicit submission and ordinary final output through the same correlated submission operation.
- Gate owner execution and already-queued input before running verification; keep a bounded attempt-correlated deferred-mail queue. Verify the existing resident adapter can establish this quiescence instead of assuming that agent settlement clears queued input.
- Apply the effective Work/Agent gate only after confirmed authoring quiescence; preserve large-result retrieval and one automatic outcome.
- Preserve verify FAIL/inconclusive escalation for all Work Items: authorize a revision before first-failure feedback resumes the owner; parked mail cannot resume execution. PASS archives deferred mail with its result.
- Correlate review authorization with the exact submission and invalidate it before release/reopen/stop, an authorized revision, or observed unexpected owner execution.
- Make failed work explicit across acquisition paths and cover recovery without implicit retries.

**Exit:** all acquisition paths require identical acceptance; same-attempt mail cannot mutate files during review, and unexpected execution cannot leave a valid PASS. Duplicate explicit/automatic results, revoked reviews, and stale gates cannot close or unlock work. Final text from unassigned residents produces no submission.

### 3. Atomic public-interface cutover

- Register explicit action schemas for agent and work plus communication-only agent_event on the established tool seam.
- Preserve generated-definition startup, unassigned residents, deliberate inspection, exact stop, and all advanced Work operations in the operation tables.
- Test these registrations through real state and controlled process events.
- Remove legacy teammate_*, task_*, send_message registrations and schemas in the same change. Replace internal prompt/template references, including verification feedback and role capability grants.
- Update system guidance and tool disclosure together; worker action authority remains runtime-checked.

**Exit:** only three coordination tool names exist, every advanced capability in the tables has a public test, no prompt or workflow references a removed name, and agent delegate has no independent lifecycle policy.

### 4. Lifecycle recovery and presentation completion

- Re-exercise the recovery and verification guards already implemented in slices 1–2 through the final tools and Console. This slice is integration coverage and presentation, not the first implementation of those safety rules.
- Update Team Console work/Presence views, result rendering, bounded histories, and role/state disclosure.
- Preserve one-shot board notices, no heartbeat/stall prompts, safe late-result retention, and resume of the same runtime scope without importing another session's work.
- Remove receipt teaching helpers and obsolete exact-wording tests only after replacement behavioral coverage is green.
- Reject incompatible persisted formats explicitly; do not erase legacy artifacts or add a migration layer.

**Exit:** diagnostics, synchronous receipts, queued intents, accepted Work results, and process cleanup remain distinguishable without duplicated coordination prose.

### 5. Release and installed-runtime acceptance

- Align runtime instructions, both root READMEs, the package README, role reference, and current specs with the new interface. Retire conflicting older design claims without overwriting historical evidence indiscriminately.
- Add a breaking-change-appropriate Changeset; validate no workspace protocols escape packed manifests.
- Run one sequential verification gate, then a fresh read-only audit. Acceptance is based on the final diff, not an earlier PASS.
- Verify actual installed extension loading, print-mode completion, and the interactive Team Console. If a provider is unavailable, record that blocker rather than equating a test fixture with live acceptance.

**Exit:** there is one supported public interface and a verified installed end-to-end product. No new state schema or tool family ships half-wired.

## Regression inventory

Tests stay under tests; primary seam is registered tools with real reducers. Existing fixtures to consult, not copy into additional layers:

- Delegation, presence, exact routes: @tests/agent-control-fixture.ts, @tests/test_agent_delegation.py, @tests/test_work_sessions.py.
- Fork/context: @tests/test_work_context.py and its real SessionManager fixtures.
- Automatic output: @tests/test_automatic_results.py; drive message and settlement events instead of asserting helper text.
- Assignment safety: @tests/test_assignment_guards.py, @tests/test_leader_priority_lifecycle.py.
- Claims, resources, supersession, verification: relevant registered-tool and state-machine cases in @tests/test_teammate_package.py.
- Reporting and cleanup: @tests/test_immediate_reports.py, @tests/test_late_report_delivery.py, @tests/test_shutdown_confirmation.py.

Add focused scenarios for authorization by action, queued claim versus accepted ownership, final answer with a board claim, empty resident final, failed acquisition without partial state, and old messages following reopen. Cover same-attempt steer/PASS, previously queued owner turns, parked mail, revision/PASS invalidation, superseded release acknowledgement, atomic parked reopen, stop/PASS ordering, confirmed-stop precedence, and prerequisite-reopen/dependent-acquisition races. Delete obsolete assertions for removed tool names and repeated advisory English as their replacement tests land. Keep stable behavioral guarantees, not the old file structure.

## Verification and scope hygiene

Expected implementation commands: package pytest, pnpm typecheck, pnpm pack:check, pnpm check:install, then pnpm check sequentially where appropriate. Avoid duplicate simultaneous full-suite runs against shared runtime files. Use actual pi --print and interactive Console scenarios after installing/reloading the new extension.

Known prior verification limits are evidence, not accepted exceptions: the previous task's package suite passed 212 tests; root checks exposed keyboard/plan-mode/utils failures and one intermittent report test; live attempts failed at provider/model access or networking. Recheck rather than calling the new implementation complete on those old results.

This planning task changes only specifications and design scenarios. It leaves the current anti-polling implementation, its Changeset, other package edits, manifests, installed settings, and memory files untouched. Before implementation, inventory the working tree and keep this slice separate from other sessions' work.

## Non-goals and deletion budget

Preserve advanced Work and residents; defer new promotion/Agent Memory/global inbox/daemon/cloud-computer work. Do not introduce a generic event-sourcing framework, transport abstraction suite, or policy engine.

The simplification is complete only when duplicate registrations, kind-dependent Work logic, terminal-message authority, and repeated result guidance are deleted. Reducing nine tool names to three while retaining all duplicate implementations does not satisfy the destination.
