# @fradser/pi-plan-mode

Minimal plan mode for Pi. Parallel explore workers + plan writer, with dedicated model support.

## Install

```bash
pi install npm:@fradser/pi-plan-mode
```

## Usage

```
/plan              Toggle plan mode (interactive menu)
/plan start        Enter plan mode (interactive planning in main session)
/plan <prompt>     Spawn parallel explore workers + plan writer
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
│  Phase 1: Parallel Explore Workers          │
│                                             │
│  ┌─────────────┐  ┌─────────────┐          │
│  │ Explore 1   │  │ Explore 2   │  ...     │
│  │ (structure) │  │ (patterns)  │          │
│  │ read/grep   │  │ read/grep   │          │
│  │ find/ls/bash│  │ find/ls/bash│          │
│  └──────┬──────┘  └──────┬──────┘          │
│         │                │                  │
│         └────────┬───────┘                  │
│                  ▼                          │
│         Explore Results                     │
└──────────────────┬──────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────┐
│  Phase 2: Plan Writer                       │
│                                             │
│  ┌─────────────────────────────────────┐    │
│  │ Plan Writer                         │    │
│  │ - Receives all explore results      │    │
│  │ - Writes plan to plans/<key>.md     │    │
│  │ - Tools: read/grep/find/ls/bash/   │    │
│  │         write (plan file only)      │    │
│  └─────────────────────────────────────┘    │
└──────────────────┬──────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────┐
│  Plan Ready — Action Menu                   │
│                                             │
│  > Implement here (this session)            │
│    Start fresh and implement (new session)  │
│    View plan                                │
│    Stay in plan mode                        │
│    Exit plan mode                           │
└─────────────────────────────────────────────┘
```

### Phase 1: Parallel Explore

Explore workers run in parallel. By default, a single explore worker covers the full codebase. For complex tasks, multiple explore workers can be specified with different focus areas:

| Workers | When to Use |
|---------|-------------|
| **1** (default) | Simple tasks, known files, small changes |
| **2-3** | Complex tasks, multiple areas, uncertain scope |

Each worker runs in isolation (`--no-session`) with read-only tools only.

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

The plan model is used for both explore workers and the plan writer.

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
