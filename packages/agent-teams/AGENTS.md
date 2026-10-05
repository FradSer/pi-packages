# Repository Guidelines

## Project Structure

`packages/agent-teams/` publishes `@fradser/pi-agent-teams`. Package root
`index.ts` re-exports `src/index.ts`. Implementation is modularized under `src/`:
`agent-actions.ts` handles agent lifecycle actions, `tools.ts` registers tool
schemas and dispatches actions, `worker.ts` registers worker-scoped tools,
`team-machine.ts` orchestrates state and task assignments, `statefile.ts` handles
atomic state persistence, `guidance.ts` injects system prompt instructions, and
`references/agent-roles.md` contains role templates. BDD contracts live in
`features/`; executable tests and fixtures live in `tests/`.

## Commands

Run from the repository root:

```bash
python3 -m pytest packages/agent-teams/tests/ -q
pnpm --dir packages/agent-teams pack --dry-run
```

## Style and Architecture

- **Tool Surface**: The bundle exposes `agent`, `task`, and `message`, each
  registered by its owning package. `/agent-teams` is the human management
  surface; obsolete tools and verbs have no compatibility registrations.
- **Agent Actions**: `start`, `send`, `interrupt`, `inspect`, `list`, and `stop`.
  Every child settles to IDLE/sendable until stop or parent shutdown. Start/send
  and public steering await correlated native RPC acknowledgement; preserve
  authority on uncertain timeout and never retarget exact incarnation handles.
- **Identity and data**: Read @../subagents/VISION.md and @../subagents/AUTHORITY.md
  before changing child controls or storage. Disk `agent.md` alone declares a
  durable identity. Inline roles are session-only. No persistence/Memory/worktree
  switches, model-created disk definitions, Git workspace or automatic commits.
  Durable data uses one private home; children edit the original project cwd.
- **Task Lifecycle**: `task` owns create/list/update/complete/reopen. Participants
  take work with `update status=in_progress`; a task declares no assignee. Failed
  results require explicit failed completion, and configured verification gates
  must not be bypassed by callback ordering or draining a report.
- **Communication**: `message` is communication-only (`inform` or `request`) and
  changes no execution ownership or acceptance. Results arrive automatically;
  continue independent work or end the turn, never poll to wait.
- **Persistence**: Communication snapshots belong to `statefile.ts`; the durable
  task storage belongs to pi-tasks. Do not duplicate either record in child identity
  or use presence as acceptance evidence.

## Testing Guidelines

`features/` holds BDD contracts (`agent-teams.feature`, `unified-work-interface.feature`,
`shared-communication.feature`, etc.); `tests/` holds Python tests and TypeScript
fixtures. Verify tool counts, atomic state transitions, assignment guards, and
delivery paths. Pack checks must include `index.ts`, `src`, `references`, `.memory`,
and `README.md`.
