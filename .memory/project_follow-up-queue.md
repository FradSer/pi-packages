---
name: follow-up-queue
description: Agent Teams report delivery can replay obsolete progress after completion because FIFO follow-ups and inline terminal results have independent consumption state
type: project
---

## Why

Agent Teams currently sends one report through Pi's `followUp` channel and holds later reports until `agent_settled`. Pi does not consume a follow-up until the leader stops calling tools. A busy coordination loop can therefore delay decision-useful reports for the entire assignment. Each remaining FIFO item then starts a separate leader run.

The leader's `send_message` result can independently expose `RECORDED TERMINAL REPORT` from the mailbox. Reading that result does not acknowledge or remove its asynchronous delivery, or any earlier queued reports. Terminal status suppresses reports received after the terminal event, not already queued progress. Pending `unfinalized-report` diagnostics are not revalidated when work later completes. These are distinct authored events replayed too late, not necessarily duplicate outbox reads.

A real session demonstrated 13 unique worker report event IDs and one harness diagnostic delivered after the leader's conclusion; the first report was delayed about 20 minutes. An isolated reproduction using the actual team machine, outbox drain, routing result, and FollowUpQueue returned the final result inline while all three reports remained pending. Existing tests passed because they explicitly require one-report-per-follow-up-turn behavior.

## How to apply

- Trace both delivery paths: `src/team-machine.ts` and `src/tools.ts` expose mailbox terminal results; `src/index.ts` and `src/follow-up-queue.ts` schedule asynchronous messages.
- Distinguish authored time, mailbox acceptance, native queue handoff, and actual model-context delivery. Queue acceptance is not proof that the leader has read a report.
- Changing global `followUpMode` to `all` cannot drain reports still held in the package's single-active-dispatch queue.
- A fix must change the behavioral contract and tests, not merely add stronger report-writing prompts. Cover a busy leader, intermediate reports followed by completion, an inline terminal result, later assignment reopening, and a resolved pending diagnostic.
- Preserve full event history separately from model wake-ups. Scope freshness and acknowledgement by event and assignment/report sequence, not only worker name or spawn: reopened assignments reuse a resident process.
- Do not drop earlier reports merely by body equality or a wall-clock TTL. Report relevance and supersession need explicit lifecycle evidence.
- During orchestration, do independent work or yield. Repeated status requests and unsolicited steers keep the leader run active and amplify the queue delay.

## Related

[[feedback_no_sleep_waiting_for_teammates]]
[[project_agent_teams_persistent_agents]]
