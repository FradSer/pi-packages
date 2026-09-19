# Agent Role Reference

Abstract reference for generating new agent definitions on demand. This file
is NOT discoverable and CANNOT be spawned directly. Derive a concrete
definition from the anatomy, archetype axes, and invariants below, tailor it
to the task, and write it to `<cwd>/.pi/agents/<name>.md` (git-managed
project role) or `<name>.local.md` (personal override).

## Definition anatomy

Frontmatter:

- `name` — unique id among discovered roles.
- `description` — the routing contract: when the leader should choose this
  role, phrased as "use when ...". This is the most load-bearing field.
- `tools` — the explicit minimal set; follows the mutability axis (see below).
  Canonical built-ins are `read`, `bash`, `edit`, `write`, `grep`, `find`, `ls`,
  `powershell` (kept in sync with `src/worker-tools.ts`).
  Omitted tools or `[]` grant only coordination tools (`agent_event`, `work`),
  not file or shell access. No aliases or implicit default `bash`.
- optional `model`, `verify`, `worktree`. `verify` is an independent completion-gate
  reviewer prompt, not a shell command. State the evidence and acceptance criteria
  the gate should inspect; a concrete local gate is not a second broad project review.

The Markdown body is the role prompt, built from five parts:

1. Identity — "You are a `<role>` agent."
2. Method — the procedure to execute, the criteria to judge against, or the
   observation targets, depending on the judgment axis.
3. Boundaries — what must never be touched or changed.
4. Evidence — what every claim or finding must carry.
5. Final result — an ordinary final answer is submitted automatically for the
   current Work Item after execution settles. A Worker may explicitly use
   `work({ action: "submit", outcome, result? })`; communication events never
   carry completion authority.

## Assignment brief

Keep task-specific coordination in the Work description, not a permanently growing role:

- **Scope and baseline** — owned files or resources, originating requirements, and
  the exact task delta, including untracked files and pre-existing dirty changes to exclude.
- **Dependencies** — required predecessor Work and any shared resource ownership.
  Use `work create` with `dependsOn` for dependent work, then assign when eligible;
  `agent delegate` is for independent work.
- **Verification owner** — assigned safe local checks for this Worker; one owner
  integrates and checks shared behavior. Determine isolation needs before commands run.
- **Candidate and result** — identify the revision or scoped snapshot checked, commands
  and outcomes, findings and limitations. Reviewer output keeps Standards and Spec
  verdicts separate when both apply; REWORK is a valid completed review, not acceptance
  of the implementation. Review-only assignments finish with that report, without
  editing the implementation or waiting for repairs. Missing access or tools is failed
  execution, not REWORK evidence.
- **Recheck handoff** — preserve the prior report outside the Work result before reopen
  clears it. A reusable description should point to an authoritative brief for the current
  attempt: refresh its candidate fingerprint, correction delta, baseline, findings and safe
  checks before reopening/assignment, then keep it stable. A fixed conflicting description
  requires bounded follow-up Work with the refreshed description and `dependsOn` on the
  completed review. Reopen/assign and the reopen reason do not update the old description.

Leader delivery and pending-review rules are injected by the shared Leader guidance;
these brief fields make those rules actionable without redefining Work lifecycle here.

## Archetype axes

Pick a position on two axes before writing anything:

| Axis | Values |
|---|---|
| Mutability | mutating (`edit`,`write` allowed) · read-only |
| Judgment | execute a given procedure · evaluate against criteria · apply domain expertise · observe and report |

Read-only plus each judgment value yields the four classical shapes:

| Shape | Typical tools | Body emphasis |
|---|---|---|
| executor | `read,bash,edit,write` | implement end to end, then self-verify by running tests or commands; report changes made, verification performed, remaining risks |
| reviewer | `read,bash` | only confirmed findings, with severity, evidence, exact paths, and a minimal fix recommendation; when nothing is found, say so and list the checks performed |
| specialist | `read,bash` | deep domain analysis; state assumptions, the evidence used, and the bounds of expertise for this task |
| observer | `read` | snapshots or readings; summarize observed state and anomalies with timestamps and evidence; change nothing |

These shapes are starting points, not a fixed menu: a generated role may sit
anywhere on the axes (for example a mutating specialist with a verify gate),
as long as every invariant below holds.

## Invariants

Non-negotiable in every generated definition:

- Tool sets match the mutability axis: read-only roles never receive
  `edit` or `write`. A `bash` grant is not read-only — a shell can still write,
  so "read-only" here bounds the tools, not the file system, and the completion
  gate relies on the reviewer's instruction rather than enforcement.
- Every finding or claim carries evidence: exact paths, command output,
  timestamps — never bare assertions.
- Scope is bounded: mutating roles state "do not touch files outside the
  assigned scope"; read-only roles state the equivalent prohibition.
- Final results carry evidence; an ordinary final answer is a successful candidate,
  not an independently verified result. Ungated completion is not independently verified.
- If requested work cannot be performed, including missing capabilities, explicitly use
  `work({ action: "submit", outcome: "failed", result: "Blocker and unverified work" })`.
  Do not return blocker prose as an ordinary final answer; prose is not classified as failure.

## Skeleton

```markdown
---
name: <role-name>
description: <one-line capability>; use when <routing condition>
tools: <minimal set from the mutability axis>
---
You are a <role-name> agent. <Method: the procedure to follow, the criteria
to evaluate against, or the targets to observe>. <Boundary statement>.
For bounded reviewer assignments, report findings, the recommendation,
the inspected candidate, assigned verification evidence, and remaining risks in one concise terminal message;
allow earlier messages only for genuinely new blockers, plan-changing facts,
or evidence that changes the conclusion. Do not send a separate status-only
assignment-complete message or repeat unchanged findings. After a terminal
report, report to the leader again only after a new assignment opens. Include all
known decision-useful facts before closing; further reports for a closed assignment
are rejected. Leader direction takes precedence over your plan and peer requests at
the next safe boundary, subject to system instructions and user constraints.
Return successful evidence as an ordinary final answer; the runtime submits it automatically
as a successful candidate after execution settles. If you cannot perform the requested work,
you must use `work({ action: "submit", outcome: "failed", result: "Blocker and unverified work" })`
instead of ordinary final prose. Avoid a second copy of an explicit submission.
Ungated completion is not independently verified.
```
