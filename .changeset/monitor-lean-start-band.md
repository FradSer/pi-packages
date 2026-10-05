---
"@fradser/pi-monitor": patch
---

Show only non-redundant fields in the expanded monitor start band.

Drop the constant `terminal · pending at start` row, because the row already
uses pi-kit's pending role. Drop the `cwd` row, because `monitor_start` has no
cwd parameter and the value always equals the session cwd. Drop the monitor id
row, because the model-facing result already carries `monitor_id` for
`monitor_stop` and the `/monitor` console keeps ids for inspection.

Show `Completion` and `Timeout` only when they differ from their defaults. A
default start now expands to the stored command and its success and failure
contracts.

Give the started band its own `Label: value` vocabulary with an uppercase first
letter on every label. A scalar field keeps the value beside its label. The
command keeps the label alone on its row and its shell syntax below it.

Highlight the command with pi's `highlightCode` under the active theme, so its
keywords, strings and operators carry the user's colors. The command is
sanitized before it reaches the highlighter.

Use the same field-name vocabulary in the terminal event band and the stop row,
so every expanded monitor field reads `Label: value` with an uppercase first
letter. The row head keeps the shared pi-kit ` · ` separator between the
outcome and the description.

Attribute what ended every run. Record the completion mode and, when the
contract rather than the process ended the run, the cause. A match-mode success
never reads like a finished command, and its compact direct reply never
collapses into a bare `status=success`. State the matched line as the contract's
own evidence, and reference it when a result or capture already carries it.

Name the next actor once a run does not pass. A `next=` line states that actor's
next move for the cause, while a passing run carries evidence instead. The
terminal row omits the monitor ID, which the `/monitor` list keeps as its
selection key.

Give the `/monitor` console the same vocabulary, the same highlighted command
block and the same contract names as the lifecycle rows. The console spends no
detail row on a description its list row already shows.