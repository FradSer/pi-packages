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

- **Tool Surface**: Exactly three public tools: `agent`, `work`, and `agent_event`.
  `/agent-teams` is the human management surface. Do not add compatibility
  registrations for obsolete lifecycle/message/task tools.
- **Agent Actions**: `agent` uses strict actions: `delegate` (new independent Work),
  `start` (unassigned resident), `inspect` (presence), and `stop` (exact session).
- **Work Lifecycle**: `work` owns task state. Leaders use `create`, `list`, `assign`,
  `release`, `reopen`, and `supersede`. Workers use `list`, `claim`, `release`,
  and `submit`. Submission triggers the verification gate when configured.
- **Communication**: `agent_event` is communication-only (`inform` or `request`).
  Never use sleep, polling loops, or status probes to wait for resident teammates;
  end the turn and await native notification.
- **Persistence**: Team state persists atomically via `statefile.ts` to
  `~/.pi/agent/teams/<session>.json`.

## Testing Guidelines

`features/` holds BDD contracts (`agent-teams.feature`, `unified-work-interface.feature`,
`shared-communication.feature`, etc.); `tests/` holds Python tests and TypeScript
fixtures. Verify tool counts, atomic state transitions, assignment guards, and
delivery paths. Pack checks must include `index.ts`, `src`, `references`, `.memory`,
and `README.md`.
