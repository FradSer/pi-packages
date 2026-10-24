# The full SDLC workflow

Read this reference when starting a change, resuming a stage, or handling a
review, release or incident. Read the command reference before running the engine.
This implements the [AI-native SDLC playbook](https://academy.claude.com/courses/ai-native-sdlc-playbook)
for Codex and Pi. Keep organization policy and existing authorization in force.

## Artifacts and ownership

One working directory or Git worktree owns one active change. INTENT.md states
what and why. SPEC.md records requirements and design. PLAN.md records how.
HANDOFF.md states the latest execution state and evidence. REVIEW.md is review
policy, not findings. Findings and approvals belong in the PR or change system.
Use `init` to create the task record without overwriting existing documents.
Update existing artifacts in place. Archive a finished task before starting the
next one. `.sdlc/tasks/<task>` keeps the artifact snapshot; add that snapshot to
version control explicitly if the team uses it as an audit record. Git commits,
reviews and protected service records remain the durable audit trail.

## 1. Plan: capture the intent

Brainstorm in the originator's words. Ask about users, scope, constraints and
measurable success when an answer changes the result. Record known facts with
the exact INTENT.md template. Unknowns stay open. Do not turn a question into a
build request. Ideas, tickets and incidents can all start this stage.
The originator corrects the draft. A product owner accepts or rejects it through
the team's approval system. Commit the accepted intent. `advance` verifies the
external approval for the exact intent digest before entering design.
Use a shared intent home, normally in the product repository. Link Jira or other
legacy records to the artifact and commit SHA. Declare which source is authoritative.
Do not silently create two competing requirements records.
Measure conversation-to-commit time, acceptance rate and changes after design starts.

## 2. Design: derive the requirements and design together

Read the approved intent, current code and relevant organization skills for
security, compliance, brand and UX. Use the bundled SPEC.md template. Number
requirements so later checks can cite them. Map each intent constraint to a design
choice and a verification method. Record applied policy versions. Carry unanswered
questions forward. Give each concern a named owner; do not resolve conflicting
policies by inventing an exception. For UI work, iterate on a mock before build.
The product owner reviews the spec and resolves concerns with their policy owners.
A technical lead joins for higher-risk work. Commit the reviewed spec next to the
intent. `advance` requires product owner approval before implementation planning.
Measure intent-to-spec time and specification rework after implementation starts.

## 3. Build: plan first, then implement

Start in read-only plan mode. Read intent and spec. Use the PLAN.md template to
name changed files, sequence, test commands, risk and rejected alternatives.
An engineer who has not seen the conversation must be able to follow it.
Configure real checks and the independent evaluation suite before plan approval.
Commit the approved plan. `advance` requires the engineer's approval before build.
When implementation changes the plan, edit and review it in the same change;
`rewind` invalidates downstream approvals and evidence.

Keep AGENTS.md (CLAUDE.md on Claude) short and specific: architecture, commands,
conventions and repeated mistakes. Record a correction after the same mistake
happens twice. Use versioned skills for organization knowledge with a named policy
owner. Test skill discovery with different user phrasings. Deterministic checks
back policies that must always hold; CI checks all write routes, including shell.
Keep fast, scoped checks on edits and heavy checks at commit or PR time.

Split independent tasks by touched files. Use a separate worktree per parallel
session. Run tasks that share files in sequence. Start with two or three streams
and increase only while human review keeps up. Repeated scoped work can use
researcher, verifier and simplifier subagents with separate contexts and tool limits.
Read-only verifier agents report results; they do not repair the code they judge.
Do not launch subagents when the user or host forbids delegation.
Measure plan rework, merged changes and rework rate together, not output alone.

## 4. Test: close the feedback loop

Give the agent executable success criteria. Run tests, build and lint as relevant.
For a defect, reproduce it with a failing test before repair. Protect the accepted
check from being weakened during the repair. For UI work, run the app, capture
screenshots, compare the intended state, and iterate. A fixture is not proof of
real service or visual behavior. Repair failures and rerun affected checks.
`check` runs configured argv commands and records actual exit codes and output.
`advance` from test requires current passing check and evaluation receipts.
A fresh verifier may perform the final check independently of the author.

Collect 20 to 50 representative real tasks for continuous evals. Pin each to a
historical source revision, expected result and allowed edit paths. Keep graders
outside the agent checkout. Evaluate the current model, prompts, AGENTS.md,
skills and hooks on configuration changes and on a schedule. Do not disable the
very setup under test. Include each production incident as a new regression.
The engine's `eval` runs isolated worktrees; CI must protect the suite, runner and
policy configuration. Measure case pass rate and escaped defects separately.

## 5. Deploy: review, approve and release

Use REVIEW.md to define bugs, security and intent/spec/plan compliance passes.
`review` invokes the configured independent reviewer and records its digest-bound
findings. Important findings stop progression. Address review comments, rerun
checks and request a fresh review. Preserve comment-to-fix evidence in the PR.
The code owner makes the merge decision through branch protection. The agent
has no authority to approve itself. Update stale project guidance when found.

Run CI agents in isolated containers with scoped, short-lived credentials and
network policy. Start with read-only failure triage; write changes through PRs.
Configure release, health/status and rollback argv adapters per environment.
Those adapters can call MCP, a CI job or a deployment CLI. Do not provide standing
production credentials to the authoring agent. Rehearse rollback in staging.
`deploy` requires a clean committed revision and current checks and review.
Development needs no release approval. Staging needs engineer approval;
production needs release-manager approval bound to the exact version and digest.
A failed release or unhealthy status invokes rollback and remains failed even if
rollback succeeds. A missing adapter or approval fails closed. Do not invoke a
release unless the user's scope authorizes the external action.
Measure time to first review, review resolution, release health and rollback result.

## 6. Maintain: restart from evidence

Pick a metric with a stable baseline. Use at most 30 days of hourly readings;
keep the latest reading out of the baseline. `metric` detects breaches without
model judgment. Above 1 sigma: log. Above 2 sigma or drift (four of five above
1 sigma, eight above the mean): diagnose read-only. Above 3 sigma: propose a
change through review; do not silently grant direct write permissions.
Pass the diagnosis through an independent deterministic check or adversarial
review before the next stage. Escalate low-confidence or conflicting results.

The diagnosis adapter returns an intent proto-spec. The engine writes a deduplicated
`.sdlc/inbox/<event>.md` and evidence JSON for product owner/on-call triage.
A scheduled job, webhook, ticket or channel adapter can call the same command.
Route accepted findings into a new worktree and the same intent-to-maintain flow.
Dismiss, schedule or fix with a recorded owner decision. Tune noisy detection.
Only externally pre-approved runbooks may bypass proposal handling; the engine
chooses the conservative PR route at 3 sigma. After a fix ships, add an incident
eval and compare the metric to its baseline. Do not equate an alert with a proven cause.
