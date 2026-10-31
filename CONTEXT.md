# Repository context

Updated: 2026-10-30. Keep this file as a repository entrypoint. Package checkpoints
own detailed implementation state, acceptance evidence and outstanding work.

## Current work and authority

The active objective is the resumed Pi 1.4.0 / gpt-6-luna continual-learning
Memory loop and its use of actual Pi work context for Memory and scoped Harness.
After native ChatGPT rejected Fast, the user approved the same Luna without Fast.
Resources remain authorized; the learning objective is still incomplete.
The native recovery reached coverage review but stored no Memory. Independent
inspection found an omitted internal implementation relation; source-bound
generation checks now preserve it. Do not redraw the held plan or bypass gates.
@TODO.md records the small Memory/control comparison after a complete real loop.

Read @packages/continual-learning/CONTEXT.md for the authoritative architecture,
latest real failure and costs, immutable source bindings, and remaining acceptance
steps. Do not duplicate its run history or treat old root-level test counts as
current package evidence. Host Pi and isolated study Pi versions are distinct.

Repository workflow and safety rules live in @AGENTS.md. Read a package's own
AGENTS.md before changing or studying it. Current source, tests and manifests take
precedence over historical descriptions; a package checkpoint must identify its
verification limits rather than imply whole-workspace acceptance.

## Package boundaries

| Package | Responsibility | Authoritative entrypoint |
| --- | --- | --- |
| `packages/kit` | Shared extension infrastructure and worker transport | `packages/kit/README.md` |
| `packages/subagents` | Agent execution, durable identity, isolated sessions and Session Results | `packages/subagents/VISION.md`, `packages/subagents/AUTHORITY.md` |
| `packages/tasks` | Durable tasks, attempts, submissions and acceptance | `packages/tasks/README.md` |
| `packages/agent-teams` | Addressed communication, presence and coordination | `packages/agent-teams/README.md` |
| `packages/loop` | Scheduled repetition of one real user message within a session | `packages/loop/README.md`, `packages/loop/AGENTS.md` |
| `packages/continual-learning` | Memory, Harness and project AGENTS.md learning | `packages/continual-learning/CONTEXT.md`, `packages/continual-learning/AGENTS.md` |

Package directories and published names can differ. Inspect the owning manifest
before changing installation or release wiring. Bundled packages remain usable
independently; shared helpers belong to pi-kit rather than copied implementations.

## Repository contracts

- Agent identity, Work Session, Process Incarnation and Task are distinct. A
  Session Result reports a settled turn; it does not establish Task Acceptance.
- Durable agent definitions and capability Memory belong to the agent. Concrete
  project facts remain Project Memory. Temporary agents cannot acquire persisted
  identity by retrospectively promoting their conversation.
- Child history is partitioned by native parent/project identity. Identity Memory
  and scratch may be shared. Reopening a parent and concurrent copies of one
  parent identity have different isolation implications; see subagents authority.
- The subagent intent surface is `agent_start`, `agent_input`, `agent_stop`,
  `agent_list` and `subagents_enable`. Retired `agent` and `agent_inspect` names
  are not active contracts; see @docs/adr/0008-retire-the-legacy-agent-tool.md.
- Tasks record work and completion gates. Messaging, an answer, a process exit or
  a successful submission does not independently transfer ownership or acceptance.
- Ordinary scratch folders provide no Git worktree, branch or write-isolation
  guarantee. Computer/resource ownership requires its own current authority.
- Learning planners propose; the parent validates and mutates. Memory is untrusted
  reference data, Harness owns execution conditions, and guidance delivery alone
  does not demonstrate compliance, adoption or improved later behavior.
- Test, print, real terminal, native lifecycle, real-model and downstream task
  evidence establish different claims. Preserve failures, unknown costs, original
  artifacts and unrelated work; do not promote a bounded pass into a full audit.

## Verification and history

Use the commands and completion gates in @AGENTS.md and the owning package.
`pnpm test`, `pnpm typecheck`, `pnpm pack:check` and `pnpm check` have different
coverage; installation checks and live Pi acceptance remain separate. Do not
reuse a past dependency cohort or historical CI result as current verification.

Full pre-compaction checkpoints are preserved outside the source tree at:
`/Users/FradSer/.codex/visualizations/2026/10/13/01a13584-6a05-79f3-91ec-68e0acd37092/continual-learning-20261026/context-before-resume-20261026/`.
`root-CONTEXT.md` and `continual-learning-CONTEXT.md` are byte-identical backups;
`manifest.json` records their original hashes. Earlier repository history remains
in Git and @docs/history/CONTEXT-archive-20261002.md. Historical open reviews and
session handles in those archives are evidence of their own time, not current
instructions to poll, restart, migrate or declare completion.
