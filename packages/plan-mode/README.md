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
│  - Writes plans/<topic>.md                    │
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

When the main-session plan is ready and Pi has settled, the review menu opens automatically without keeping the agent busy. Dismiss it to continue prompting, or choose an implementation action. You can also use `/plan review` or the plan-mode menu to inspect the plan. The agent decides automatically whether worker research is required; users do not need to invoke a separate research command.

### Read-only bash

Plan mode validates every command in `&&` chains and `|` pipelines, for example:

```bash
ls -la packages/matt-pocock/ && echo "---" && ls -R packages/matt-pocock/ | head -80
```

Quotes preserve spaces and literal operators. Only bare allowlisted command names
are accepted. Redirects, substitutions, escapes, newlines, background jobs,
comments, unquoted shell expansions, and other shell operators are blocked.
An unsafe or malformed stage blocks the entire request.

Commands with write or execution modes use restricted option lists: for example,
`find -exec`/`-delete`, `sort -o`, and Git mutation/output/external-diff options are
blocked. Git branch, tag, and remote commands are listing-only. Basic `diff`,
`jq`, ripgrep context options, and Git log formatting remain available.
Interactive `less` and write-capable `yq` are not allowed; use the read tool or
simpler inspection commands instead. This is a conservative command guard, not an
OS sandbox: it assumes trusted executables and local Git configuration.

### Automatic worker research

When the plan marks worker research as required, explore workers run automatically. By default, a single explore worker covers the full codebase. For complex tasks, multiple explore workers can be specified with different focus areas:

| Workers | When to Use |
|---------|-------------|
| **1** (default) | Simple tasks, known files, small changes |
| **2-3** | Complex tasks, multiple areas, uncertain scope |

Each worker runs in isolation (`--no-session`) with read-only tools only. While they are active, the live worker widget is rendered above the input editor, matching the agent-teams worker display.

### Phase 2: Plan Writer

Receives all explore results as context and updates the same readable plan file as the main session.

### Post-Plan Actions

After plan generation, choose what to do:

- **Implement here** — Exit plan mode, send plan as context to current session
- **Start fresh and implement** — Create a new linked session with plan context
- **View plan** — Display the plan content
- **Stay in plan mode** — Continue exploring/refining
- **Exit plan mode** — Discard and exit

## Plan File

Plans are stored at `~/.pi/agent/plans/<topic>.md`, for example `repair-completion.md`:
- The first `/plan <prompt>` supplies the topic; `/plan start` waits for the first planning prompt.
- Filenames preserve Unicode letters and numbers, use hyphens between words, and limit the topic to 60 characters. Punctuation-only topics use `plan`.
- Existing names are never overwritten during allocation: collisions receive `-2`, `-3`, and so on. An empty file reserves the name but does not trigger review.
- The exact path is saved in session history and restored on reload, resume, and branch navigation. Further requests in that session retain it; worker research, review, and fresh implementation share that reference.
- `PI_CODING_AGENT_DIR` overrides the agent directory. Ephemeral sessions retain the reference only for their lifetime.

Existing hash-named files are not renamed or automatically adopted. Conversations may still reference them. To continue an old plan with a readable name, start a new planning request and ask the agent to copy the old plan into the newly assigned path; leave the original intact while other sessions reference it.

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

The plan model is used for the main planning session and, when the agent decides research is required, both explore workers and the plan writer. Worker processes have no wall-clock timeout; they stop when they exit or are aborted. Exiting plan mode, replacing the session, or starting another plan cancels pending research and review. Cancelled workers cannot overwrite the plan or open a stale review.

## Design Comparison

| Feature | Claude Code | This package | narumiruna/pi-plan-mode |
|---------|-------------|--------------|------------------------|
| Source lines | ~200 | ~750 | ~4,600 |
| Parallel explore | yes | **yes** | no |
| Plan worker | subagent | **child process** | main session |
| Model switching | no | yes | no |
| Plan file | scratchpad | `~/.pi/agent/plans/<topic>.md` | in-memory |
| Post-plan actions | approve/reject | **5-option menu** | complex state machine |
| Custom tools | 0 | 0 | 2 |

## License

MIT
