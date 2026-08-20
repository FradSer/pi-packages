# @fradser/pi-plan-mode

Minimal plan mode for Pi. The main session plans first; the agent automatically runs worker research only when the plan requires it.

## Install

```bash
pi install npm:@fradser/pi-plan-mode
```

## Usage

```
/plan              Toggle plan mode (interactive menu)
/plan start        Enter plan mode (interactive planning in main session)
/plan <prompt>     Start read-only planning in the main session
/plan exit         Leave plan mode
/plan model        Set the dedicated planning model
/plan model provider/model   Set model directly
/plan status       Show current state
```

## Architecture

```
/plan <prompt>
      │
      ▼
┌─────────────────────────────────────────────┐
│  Main Session — Plan First                   │
│                                             │
│  - Enters read-only plan mode               │
│  - Explores the codebase directly           │
│  - Writes plans/<key>.md                    │
│  - Decides whether worker research helps    │
└──────────────────┬──────────────────────────┘
                   │ optional, explicit choice
                   ▼
┌─────────────────────────────────────────────┐
│  Worker Research                             │
│                                             │
│  - Parallel explore workers when useful     │
│  - Plan writer receives the existing plan   │
│  - Live status is rendered above the input  │
└──────────────────┬──────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────┐
│  Plan Review                                 │
│                                             │
│  > Implement here                           │
│    Start fresh and implement                │
│    View plan                                │
│    Stay in plan mode                        │
│    Exit plan mode                           │
└─────────────────────────────────────────────┘
```

### Main-session planning

`/plan <prompt>` never starts child workers immediately. It enters read-only mode and sends a follow-up to the current session. The main session decides whether the request is simple enough to plan directly. This avoids unnecessary worker cost and keeps the planning context in the current conversation.

When the main-session plan is ready, use `/plan review` or the plan-mode menu to inspect it. The agent decides automatically whether worker research is required; users do not need to invoke a separate research command.

### Automatic worker research

When the plan marks worker research as required, explore workers run automatically. By default, a single explore worker covers the full codebase. For complex tasks, multiple explore workers can be specified with different focus areas:

| Workers | When to Use |
|---------|-------------|
| **1** (default) | Simple tasks, known files, small changes |
| **2-3** | Complex tasks, multiple areas, uncertain scope |

Each worker runs in isolation (`--no-session`) with read-only tools only. While they are active, the live worker widget is rendered above the input editor, matching the agent-teams worker display.

### Phase 2: Plan Writer

Receives all explore results as context, writes a structured plan to `~/.pi/agent/plans/<session-key>.md`.

### Post-Plan Actions

After plan generation, choose what to do:

- **Implement here** — Exit plan mode, send plan as context to current session
- **Start fresh and implement** — Create a new linked session with plan context
- **View plan** — Display the plan content
- **Stay in plan mode** — Continue exploring/refining
- **Exit plan mode** — Discard and exit

## Plan File

Plans are stored at `~/.pi/agent/plans/<session-key>.md`:
- Session-specific (key derived from session file hash)
- Different sessions don't interfere
- Survives session restart

## Configuration

Config at `~/.pi/agent/plan-mode.json`:

```json
{
  "provider": "anthropic",
  "model": "claude-3-5-haiku"
}
```

Or via environment:

```bash
export PI_PLAN_MODE_MODEL="anthropic/claude-3-5-haiku"
```

The plan model is used for the main planning session and, when the agent decides research is required, both explore workers and the plan writer. Worker processes have no wall-clock timeout; they stop when they exit or are aborted.

## Design Comparison

| Feature | Claude Code | This package | narumiruna/pi-plan-mode |
|---------|-------------|--------------|------------------------|
| Source lines | ~200 | ~750 | ~4,600 |
| Parallel explore | yes | **yes** | no |
| Plan worker | subagent | **child process** | main session |
| Model switching | no | yes | no |
| Plan file | scratchpad | `~/.pi/agent/plans/<key>.md` | in-memory |
| Post-plan actions | approve/reject | **5-option menu** | complex state machine |
| Custom tools | 0 | 0 | 2 |

## License

MIT
