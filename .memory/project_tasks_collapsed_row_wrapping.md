---
name: "project_tasks_collapsed_row_wrapping.md"
description: "`@fradser/pi-tasks` collapsed rows wrap the full headline without eliding, using pi-kit `authoredInlineRows`/`wrapAt`; lifecycle-row test assertions must normalize line padding before asserting phrases across wrap boundaries."
type: project
---
At a 48x24 native capture the user rejected elided collapsed rows such as `[tasks] update... (blocked) · ctrl+o to expand` and `[tasks] up... (in progress) · ctrl+o to expand` (`不允许存在`), and required the whole row to display, allowing up to three lines.

In `packages/kit/src/index.ts`, a single-line authored subject with a hint renders through `authoredInlineRows`: it wraps the title at `contentWidth - visibleWidth(hint)` through the injected `wrapDetail` (`wrapAt`) and appends the realised hint to the last line; if that width is below 1, the subject wraps at `contentWidth` and the hint is fitted on its own line.

The implementation comment records that such a one-line authored subject is never elided: the row grows by lines instead of losing words, and the realised hint follows on the last line.

`authoredInlineRows()` replaces the previous `collapsedBandRows(...)` call only on the single-line authored branch; when the subject is block-authored, contains CR/LF, or there is no hint, the row still builds `subjectRows`.

`packages/tasks/src/rows.ts` binds the shared lifecycle geometry with `fit: truncateToWidth`; the geometry's per-line fit is host truncation, while pi-kit performs the wrapping at the reduced width.

Observed native captures after the change: at 120x40 each row stays on one line; at 48x24 `[tasks] update · #1` is followed by `Recovery task (in progress) · ctrl+o to expand`, with no ellipsis.

In `packages/tasks` lifecycle-row tests, wrapped output lines are padded to the full row width, so `' '.join(lines)` leaves padding inside a phrase and a headline spanning a wrap fails a substring assertion (e.g. `[tasks] create · #1 Long               ` + ` task (pending) · to expand             `).

Why: the user rejected elided narrow rows and required the full row, allowing three lines. How to apply: for pi-tasks rows rendered through pi-kit's shared lifecycle geometry, wrap a single-line authored subject at the width the native hint leaves and keep the hint on the last line; preserve the `subjectRows` path for multi-line, block-authored and hintless subjects, and do not reintroduce middle elision. In test assertions, normalize whitespace across joined lines before asserting phrases that can cross wrap boundaries, e.g. `' '.join(' '.join(lines).split())`.
