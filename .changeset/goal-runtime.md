---
"@fradser/pi-goal": minor
---

Add thread-scoped durable goals with one `/goal` command.

Set an objective with `/goal <text>`. View the current
goal with `/goal`, and manage it with pause, resume, and clear arguments.
Keep the passive pi-kit status row below the editor, flush-left, with whole-minute time.

Collect bounded runtime verification observations separately from executor claims.
Keep the completion checker tool-less. Keep a completed goal's terminal record
without writing an archive. Preserve thread ownership and reject stale continuation or completion results.

Stop after three valid explicit final refusals, with the unmet requirement and recovery advice.
Stop empty continuation after three runs without completed work. Pending monitor acknowledgements
are not completed verification. Preserve actual monitor terminal outcomes and attributed review results.

Include offline native CLI and TUI E2E checks for completion, refusal, empty-loop bounds,
activation, pause/resume/clear, state display, and bounded process cleanup.

Keep `research_goal` blocking. It mounts no widget above the editor, reads `[goal] Researching...`
while the child works, and renders the child's latest activity on its own row beneath it through
markdown. The result row reads `Research ready` with no character count.

Read the below-editor status row as `<verb> · <elapsed>`, for example `Pursuing goal · 12m`
or `Goal paused · 12m`, with no `[goal]` tag in any state. Every verb already names the
goal, so the tag would repeat it on every line below the editor. The transcript rows
keep the tag.

Accept `update_goal`'s `completion_summary` without a length cap. The completion check
reads a bounded prefix and states the truncation, while the goal record keeps the full claim.

Accept an objective without a length cap too, in the tool schema and in record normalization,
so a long objective is neither rejected nor quietly shortened. The injected note and the
completion check each read a bounded prefix and state the truncation.

Use the session's model for the completion check and for research when no goal model is
configured, instead of leaving the child to pick up the persisted CLI default. Read global
defaults from `~/.pi/agent/goal.json`; a project `.pi/goals/settings.json` overrides it.
