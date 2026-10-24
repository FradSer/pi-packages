# Engine and integration contract

Run `python3 <skill-directory>/scripts/sdlc.py ACTION --cwd <worktree>`.
On Pi, use the `sdlc` tool with `action` and optional `args` (a JSON object string).
Python 3.11+ and Git are required on both hosts. The runner adds no model call
unless a configured review, eval or diagnosis adapter makes one.

## Actions

- `init --args '{"task":"claim-status"}'`: preserve root intent and handoff;
  create `.sdlc/state.json`, a default config and a scoped ignore file.
- `status`: show current stage, approvals and receipts.
- `advance`: check the current stage and enter the next one. Order:
  intent, design, plan, build, test, review, deploy, maintain.
- `rewind --args '{"stage":"design"}'`: invalidate later approval and evidence.
- `handoff`: check required sections, relative intent link and the 200-line bound.
- `check`, `eval`, `review`: run real adapters; return nonzero on failure.
- `deploy --args '{"environment":"staging"}'`: release, check health and roll back
  on failure. Allowed environments are dev, staging and production.
- `metric --args '{"event":"incident-123","readings":[...],"evidence":"metrics query reference"}'`:
  classify at least 25 finite hourly readings and write a triage intent at tier 2+.
- `archive`: snapshot a task that reached maintain. Do not delete the active files.
  Use another worktree for a new task, or replace summaries explicitly after archiving.

## Project config

Commit `.sdlc/config.json`. A plan approves its exact digest. Example:

```json
{
  "version": 1,
  "checks": [
    {"name":"tests", "argv":["pnpm","test"], "timeout":120},
    {"name":"build", "argv":["pnpm","build"], "timeout":120}
  ],
  "agentFiles": ["AGENTS.md"],
  "evalSuite": "/managed/sdlc/evals.json"
}
```

Use actual project commands. Each command runs without a shell. An argv may call
a reviewed script when shell behavior is needed. Commands have a 1..900 second
limit. Output is bounded. Failed or stale receipts never approve a transition.
The current Git revision, source contents, config and artifact summaries bind
verification evidence. Commit before the final check/eval/review cycle. A new
commit invalidates evidence. Hook source quotations and lifecycle updates do not
change the approved intent summary or code digest.

## Managed policy

Set `SDLC_POLICY_FILE` to an absolute JSON file outside the working directory.
The deployment/CI administrator must make this file and its commands read-only to
the agent. The engine does not claim that an outside path alone enforces ownership.
Do not place secrets in the policy or return secrets in adapter output.

```json
{
  "version": 1,
  "approve": ["/managed/sdlc/verify-approval"],
  "review": ["/managed/sdlc/review"],
  "diagnose": ["/managed/sdlc/diagnose"],
  "environments": {
    "staging": {
      "release": ["/managed/sdlc/release-staging"],
      "status": ["/managed/sdlc/status-staging"],
      "rollback": ["/managed/sdlc/rollback-staging"]
    }
  }
}
```

Adapters receive one JSON object on stdin. They return JSON on stdout and exit
nonzero on failure. An approval request contains task, stage, role and digest.
The verifier must independently query the PR/change system and return those exact
fields plus `approved: true`, `approver` and `reference`. A missing response,
wrong digest or wrong role is rejected. No engine action creates approval.
Approvals must apply to the exact revision; a verifier must reject expired or
revoked approvals. Role mapping: product-owner for intent/design, engineer for
plan/staging, code-owner for review, release-manager for production.

The reviewer receives task, digest, required passes and artifact paths. It returns
`digest`, `passes: ["bugs","security","compliance"]`, `important` (integer) and
`findings` (array). It runs independently of the author. Zero Important findings
is required; this result does not replace code owner approval.
Release/status/rollback receive task, environment, digest and Git version. Status
must return `{"healthy":true}` to pass. Diagnosis receives the metric tier,
baseline, latest value, event and evidence. It returns `{"intent":"# Intent: ..."}`.
The service must enforce read-only diagnostic tools. A production route must also
require approval in the deployment service itself; local hooks are not a sandbox.

## Independent eval suite

Keep the suite, its runner and graders outside the worktree and read-only to the
agent. Example case (`checks` run from the grader's external installation):

```json
[{
  "name":"no-sensitive-logging",
  "from":"<historical-commit>",
  "prompt":"Add request diagnostics without logging personal information.",
  "mayChange":["src/routes","tests/routes"],
  "runner":["/managed/sdlc/run-agent"],
  "checks":[["/managed/sdlc/check-no-pii"]],
  "timeout":120
}]
```

The runner reads `prompt` and `cwd` from stdin. It invokes the installed Codex or
Pi CLI with the current agent configuration enabled. It must enforce permissions,
network and edit limits. The engine creates a fresh worktree for each historical
baseline, copies configured current agent files, and detects tracked, untracked,
deleted and committed changes outside `mayChange`. It grades from the independent
suite, records per-case exit codes and removes only the worktree it created.
Do not point a grader at an agent-editable helper or use a fixture to claim model quality.

## Host guards and limits

The default input hooks still capture requests. On managed tasks the host checks
HANDOFF structure before reporting a normal finish. It reports missing evidence;
it does not restart an aborted task or infer semantic correctness.
The full stage engine runs explicitly through the skill/CLI or Pi tool. Host
write guards cover native edit tools and configured release tools. Shell, alternate
APIs and disabled hooks require CI checks, managed permissions and service-side
authorization. Do not claim local stage files are tamper-proof audit records.
Use protected branches and an approval service the author cannot write.

Configure scheduled and change-triggered CI to call `eval`, verify the PR against
intent/spec/plan, and require its status check. Use the example CI workflow only
after replacing its runner and managed-policy paths. Missing integration is a
visible blocked stage, never a synthetic pass.

Read [the CI workflow example](../templates/agent-evals.yml) when installing continuous
evaluation. The managed runner's `/managed/sdlc/ci-evaluate` entrypoint can invoke
`python3 <installed-skill>/scripts/ci_eval.py "$1"`. It runs the same independent
evaluator without creating or approving a development task. Set `SDLC_EVAL_IMAGE`
to the organization's pinned, isolated runner image. Put model credentials only
in the sandboxed agent runner's secret channel. The example grants read access
only and does not deploy, post comments or approve a PR. Configure the resulting
check as required in branch protection through the repository administrator.

## Ready host and GitHub adapters

Use `python3 <installed-skill>/scripts/run_agent.py codex` or the `pi` variant
as an eval case runner. The managed environment supplies the model, credentials,
network policy and trusted host configuration. The runner keeps skills, hooks and
project instructions enabled. It does not approve prompts or bypass hook trust.
Budget real-model evaluations separately; local scripted E2E is not such an eval.

For GitHub-backed approvals, install the bundled `github_approval.py` and `sdlc.py`
read-only together outside the agent checkout. Set the policy's `approve` argv to:

```json
["python3", "/managed/sdlc/github_approval.py", "--repo", "owner/product", "--pr", "123", "--roles", "/managed/sdlc/roles.json"]
```

`roles.json` maps each role to authorized GitHub logins. The adapter uses the
installed `gh` CLI to read PR and review records; it does not post a review or
change a branch. It requires clean committed artifacts and the exact PR head.
A later review or dismissal supersedes an earlier approval. The author cannot
supply code-owner or release-manager approval. The administrator owns the role
mapping and decides whether PR reviews satisfy the organization's release policy.
Use the change system's own verifier when approval requires a change ticket.
Keep branch protection and service-side release authorization enabled.

`metric` is stateless and works without an active development task. The
[monitor workflow](../templates/metric-monitor.yml) runs hourly in a managed image.
Its monitor entrypoint queries the metrics store, assigns a stable incident id,
and invokes the engine's `metric` action with the readings and evidence reference.
Keep the query and event source adapter outside the agent's control. The workflow
uploads the generated intents for triage and grants no repository write access.
An authorized PR/service adapter can route accepted findings to a new worktree;
product owner approval or an independent confidence gate still decides progression.
