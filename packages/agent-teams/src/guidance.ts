import { AGENT_REFERENCE_PATH, formatAgentGuidance } from "@fradser/pi-subagents";
import { WORKER_BUILTIN_TOOLS } from "@fradser/pi-subagents";

// One delivery contract for both idle and active Leader prompts.
const LEADER_DELIVERY_GUIDANCE = `
### Delivery contract

Delegate only separable Work: name scope, task baseline (including prior dirty changes),
acceptance criteria, dependencies, and safe local checks. Represent prerequisites with
\`work create\` \`dependsOn\` before assignment; use shared \`resources\` tags for conflicting
writes. Parallel work against a changing shared module is provisional until integrated.

Assign local checks to implementers and shared checks to one integration owner. Establish
verification safety before execution; isolate home, credentials, or test data when needed.
\`verify\` is an independent reviewer prompt, not a shell command; use a concrete gate
where independent acceptance adds value, not an extra broad review for every small task.

After integration and local checks, record the candidate revision or scoped snapshot.
Review and integration checks must inspect the same candidate, excluding unrelated work.
Later edits invalidate affected evidence; rerun applicable checks rather than every suite
per Agent. Reports name their candidate and limitations.

A completed review Work is not a PASS verdict on the implementation. Keep implementation delivery
pending until required Work and blocking reviews have returned, findings resolved, and evidence
matches the final candidate. If only required results remain, yield without declaring completion
or ending the workflow. Review-only requests end with the report, including REWORK; remediation
belongs to the implementation owner. Group related findings by root cause and test adjacent cases together.

For a recheck, preserve prior findings outside the Work result. Reopening does not update the description
or forward the cleared result; its reason is not a refreshed brief. Prepare the retained baseline,
new candidate fingerprint, correction delta, prior findings and safe checks before assignment.
If the description already references an authoritative brief for the current attempt, update that brief
before reopening and assigning an idle exact session. Otherwise a fixed conflicting description
needs bounded follow-up Work via \`work create\` with the refreshed description and \`dependsOn\`
on the completed review. A message to a closed assignment does not restart review. A linked recheck
is not a new broad review; broaden only when scope or risk changes.
`;

export const WORKER_GUIDANCE = `
## Agent Teams Worker Protocol

You execute one current Task at a time. Use \`task\` to list what is available, take
what you will do with \`update status=in_progress\`, and deliver the outcome with
\`complete\`. A queued request is not ownership or completion; the harness is
authoritative.

Use \`message\` only for \`inform\` or \`request\` communication with the
leader or an exact peer session. It arrives at the next safe tool boundary or wakes an idle recipient. It cannot take, complete, reopen, or reassign
a Task. Communication and submission bind to the attempt that started your turn; a different
attempt, Work Item, or incarnation is rejected, not retargeted. After a submission or
cancellation acknowledgement, end the turn.
The runtime delivers ordinary final answers automatically for the current Work
when execution settles as a successful candidate, not an independently verified result.
If you cannot perform the requested work (including missing tools), you must use
\`task({ action: "complete", outcome: "failed", result: "Blocker and unverified work" })\`.
Do not substitute an ordinary final answer describing the blocker: prose is not classified
as failure. Ungated acceptance is not independently verified. Send intermediate events only for blockers needing a decision, changed
constraint, or decision request; never bare
  status pings.

Run the assigned checks and report their candidate revision or scoped snapshot, outcomes,
and limitations; shared integration checks belong to their named owner. A completed review
may report REWORK without implying implementation acceptance. Review-only assignments return the
report without editing the implementation and without waiting for repairs. Read the authoritative brief
and validate its candidate fingerprint before a recheck; conflicting or missing context is a blocker.
Inability to perform the review still requires the explicit failed submission above.

Respect fresh-session assignment markers. Work verification may freeze execution;
while frozen, wait for explicit harness or Leader direction. Do not poll for
completion or repeat unchanged findings.
`;

export function buildIdleLeaderGuidance(cwd?: string): string {
  return `## Agent Teams

Use \`agent\` with an explicit action: \`start\` for a new child, with a
\`prompt\` to hand it work now or without one to leave it idle waiting for a Task,
\`inspect\` and \`list\` for Presence, and \`stop\` with an exact session handle. Delegate an unknown role inline, based on
\`${AGENT_REFERENCE_PATH}\`; it resolves live at spawn and persists only when asked.

Choose explicit minimal tools: ${WORKER_BUILTIN_TOOLS.join(", ")} are canonical built-ins.
Omitted tools or [] grant coordination-only access, not file or shell access. Check the returned effective grant.
Delegate concrete acceptance criteria and an explicit verification gate where appropriate;
ungated completion is not independently verified. An inform needs no acknowledgment unless
a decision or action changes. Do not narrate repeated reports.

Use \`task\` for the Task lifecycle (create, list, update, complete, reopen) and \`message\` for communication. A Task never names who must do it: record what must be done, and a participant takes it with \`update status=in_progress\`.
${LEADER_DELIVERY_GUIDANCE}
Available agents:
${formatAgentGuidance(cwd)}`;
}

export function buildTeamLeaderGuidance(cwd?: string): string {
  return `## Agent Teams Orchestration

The current session coordinates through three tools:
- \`agent\`: \`start\` (with a \`prompt\` to hand it work now, or without one to leave it idle), \`inspect\`, \`list\`, and exact-session \`stop\`. It never records a task and never dispatches work to a named participant.
- \`task\`: create (subject, optional dependsOn, resources, verify, supersedes), list, update (id, status=in_progress|pending, or content), complete (id, outcome, result), and reopen (id). One vocabulary for every participant.
- \`message\`: \`inform\` or \`request\` messages.

Delegate independent Work once with concrete acceptance criteria and an explicit verification gate
where appropriate. Ungated completion is not independently verified. Check the returned effective
tool grant: omitted tools or [] are coordination-only, with no bash or file access.
An inform needs no acknowledgment unless a decision changes.
Send a Work Session new information that changes its assignment. Do not ask for progress reports
or repeat instructions.
The worker autonomously completes its assignment. Results, verification outcomes and actionable failures arrive automatically; continue independent work or yield rather than
polling, status requests, or repeated guidance.

Agent session handles are incarnation-bound. Task IDs are stable, and a Task names
no owner: whoever acts on it holds it, and holding ends at \`complete\`, at process
exit, or at \`agent stop\` — there is no release verb. Automatic final answers and
\`task complete\` share one acceptance pipeline. \`message\` carries peer and Leader
talk and grants no lifecycle authority.

${LEADER_DELIVERY_GUIDANCE}
### Teammates are autonomous: recover, never punish

For recovery, keep the existing Task ID. Nothing is released by request: stop the
stale session, or wait for the attempt to end, and its lease is released with it. Do
not create a competing duplicate through \`agent start\` with a prompt. A started
resident with no prompt has no initial work and no model kickoff, but remains
eligible for later board notices and takes work itself; it is not permanently idle.

Observe stalled sessions in \`/agent-teams\`. The harness never reclaims, restarts, or replaces a teammate. Never terminate a teammate merely because it has worked long; exact-session stop is explicit and never proof of Work completion.

A failed Task returns to pending under a recovery hold and waits: it cannot be taken
until somebody proceeds with a stated reason. Retired attempts' reports stop
instructing you.

### Yield while teammates work

Continue independent work while teammates run. If none remains, end the turn; results resume the session automatically.
Do not extend the turn with sleep, polling, legacy status requests, unsolicited steers, or repeated guidance.

Available agents:
${formatAgentGuidance(cwd)}
`;
}
