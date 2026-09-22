# @fradser/pi-plan-mode

Generate a plan in a minimal read-only Pi subagent, then choose where to implement it through Pi's native TUI.

```bash
pi install npm:@fradser/pi-plan-mode
```

## Plan and implement

Enter `/plan <prompt>` in Pi. The command starts **one** child through pi-kit's
`runPiWorker({ minimal: true })`; the parent session does not generate the plan.
The child explores using only `read`, `grep`, `find`, and `ls`. It has no bash,
write, edit, or extension tools. Extensions, skills, prompt templates, context
files, themes, and child session persistence are disabled.

The child returns the plan as text. After successful, non-empty completion, the
host saves it to the session's assigned plan file. A passive widget shows worker
activity while planning. The planning model can be configured separately; the
parent session keeps its current model.

When the plan is ready, Pi opens its native selection menu:

- **Implement in current session** sends the saved plan to the current session.
- **Implement in new session** creates a linked session with the same plan path
  and content, then starts implementation there.
- **Stay in plan mode**, or Escape, keeps the plan for later review.

There is no automatic selection or implementation timeout. Use `/plan review`
to reopen the menu. If a new session is unavailable or creation is cancelled,
implementation does not fall back to the current session.

## Commands

```text
/plan <prompt>               Generate a plan with a minimal read-only subagent
/plan                        Open the plan-mode menu
/plan review                 Choose where to implement the saved plan
/plan exit                   Cancel planning and leave plan mode
/plan model                  Choose the dedicated planning model
/plan model provider/model   Configure the model directly
/plan status                 Show state, model, and plan path
/plan start                  Enter the existing interactive main-session mode
```

`/plan start` remains available for interactive planning in the current session.
It waits for the first ordinary planning prompt and opens the same native review
menu when the plan is ready. Re-entering this mode preserves the original model
for restoration on exit.

Headless planning also awaits the child before returning:

```bash
pi --print "/plan Inspect the project and plan the requested change"
```

It saves the plan and reports its path without starting implementation.

## Read-only boundaries and cancellation

In the parent session, genuine built-in `read`, `grep`, `find`, and `ls` are
allowed. `write` and `edit` can target only the assigned plan file. Bash uses a
conservative command guard that validates every chain and pipeline stage;
redirects, substitutions, unsafe options, and mutating Git operations are blocked.
Extension tools, including overrides of built-in names, are blocked.

The parent bash guard assumes trusted executables and local Git configuration;
it is not an OS sandbox. The minimal child has no bash tool at all.

Exiting, replacing the planning request, or changing sessions aborts the owning
child and selector. Late results cannot overwrite the plan or start implementation.
Workers have no wall-clock timeout. Explicit standalone requests such as
`implement the plan` or `执行这个计划` can leave the parent planning mode;
negations, questions, quotations, and extension-generated input cannot.

## Plan files

Plans live at `~/.pi/agent/plans/<topic>.md`, or under `PI_CODING_AGENT_DIR` when
set. Filenames preserve Unicode letters and numbers, use hyphens, and limit the
topic to 60 characters; punctuation-only topics use `plan`.

Names are reserved without overwriting existing plans; collisions receive `-2`,
`-3`, and so on. The exact path is stored in session history and reused on reload,
resume, and branch navigation. New implementation sessions retain that reference.
Empty reservations do not count as completed plans. Legacy hash-named plans remain
untouched. Exiting plan mode preserves the saved file.

## Model configuration

Use `/plan model provider/model`, or configure `~/.pi/agent/plan-mode.json`:

```json
{
  "provider": "your-provider",
  "model": "your-model"
}
```

`PI_PLAN_MODE_MODEL=provider/model` is a fallback when the corresponding saved
configuration is absent. Without a dedicated model, the child uses the current
session's model. That provider must be available to a minimal Pi process through
its normal model configuration and authentication; providers registered only by
parent extensions are not loaded in the child.

## License

MIT
