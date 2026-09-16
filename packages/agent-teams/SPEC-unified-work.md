# Agent Teams final surface

Status: final public-surface contract.

Agent Teams exposes `agent`, `work`, and `agent_event`; `/agent-teams` is the
human management surface. Legacy lifecycle, task, and message tools are absent.

- `agent` has strict `delegate`, `start`, `inspect`, and exact-session `stop` actions.
- `work` owns Work lifecycle. Leaders create/list/assign/release/reopen completed Work/supersede; Workers list/claim/submit/release current Work.
- `agent_event` is communication-only with `inform` and `request` intent.

Session handles are incarnation-bound (`session:<name>:<spawnId>`). Work
assignment requires an exact current session handle. Automatic final answers and
explicit Work submit share acceptance, verification, stale-result rejection, and
deferred-mail history. Incompatible persisted runtime snapshots fail explicitly.

Behavior is specified by @features/unified-work-interface.feature and validated
through registered-tool seams and final installed-runtime checks.
