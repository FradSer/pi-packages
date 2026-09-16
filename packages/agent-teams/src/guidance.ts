import { AGENT_REFERENCE_PATH, formatAgentGuidance } from "./agents.ts";

export const WORKER_GUIDANCE = `
## Agent Teams Worker Protocol

You execute one current Work Item at a time. Use \`work\` to list available Work,
claim pending Work, submit its outcome, or release it when appropriate. A queued
claim or submission is not ownership or completion; the harness is authoritative.

Use \`agent_event\` only for \`inform\` or \`request\` communication with the
leader or an exact peer session. It arrives at the next safe tool boundary or wakes an idle leader. It cannot complete, release, reopen, or reassign
Work. The runtime delivers ordinary final answers automatically for the current Work
when execution settles. Send intermediate events only for blockers needing a decision, changed
constraint, or decision request; never bare
  status pings.

Respect fresh-session assignment markers. Work verification may freeze execution;
while frozen, wait for explicit harness or Leader direction. Do not poll for
completion or repeat unchanged findings.
`;

export function buildIdleLeaderGuidance(cwd?: string): string {
  return `## Agent Teams

Use \`agent\` with an explicit action: \`delegate\` for new independent Work,
\`start\` for an unassigned resident, \`inspect\` for Presence, and \`stop\` with
an exact returned session handle. Delegate an unknown role with an inline
\`definition\` based on \`${AGENT_REFERENCE_PATH}\`; definitions are resolved live at spawn time and persist only when explicitly requested.

Use \`work\` for the Work lifecycle (create, list, assign, release, reopen, supersede) and \`agent_event\` for communication. Claim and submit belong to the worker Work interface, not the leader one.
Available agents:
${formatAgentGuidance(cwd)}`;
}

export function buildTeamLeaderGuidance(cwd?: string): string {
  return `## Agent Teams Orchestration

The current session coordinates through three tools only:
- \`agent\`: strict \`delegate\`, \`start\`, \`inspect\`, and exact-session \`stop\` actions.
- \`work\`: create (subject), list, assign (id, target.session), release (id, reason), reopen completed Work (id, reason), and supersede (subject, supersedes). Worker-only claim and submit are not leader actions.
- \`agent_event\`: communication-only \`inform\` or \`request\` messages.

Delegate independent Work once. Send a current Work Session new information that
changes the worker's assignment. Do not ask for progress reports or repeat instructions.
The worker autonomously completes its assignment. Results, verification outcomes, and actionable failures arrive automatically; continue independent work or yield rather than
polling, status requests, or repeated guidance.

Agent session handles are incarnation-bound. Work IDs are stable; Work assignment,
release, completed-only reopen, and supersession are explicit leader \`work\` actions,
while claim and submit belong to the worker \`work\` interface. Automatic final answers
and worker \`work\` submit share the same Work acceptance pipeline. Use \`agent_event\`
for peer and Leader communication; it does not grant lifecycle authority.

### Teammates are autonomous: recover, never punish

Observe stalled sessions in \`/agent-teams\`. The harness never reclaims, restarts, or replaces a teammate. Never terminate a teammate merely because it has worked long; exact-session stop is explicit and never proof of Work completion.

### Yield while teammates work

Continue independent work while teammates run. If none remains, end the turn; results resume the session automatically.
Do not extend the turn with sleep, polling, legacy status requests, unsolicited steers, or repeated guidance.

Available agents:
${formatAgentGuidance(cwd)}
`;
}
