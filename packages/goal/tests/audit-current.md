# Package audit — every module and every documented surface

Scope: the whole of `packages/goal`, for the "thoroughly check and optimize" goal.
Each row states what was looked for and the verdict. Defects cite file:line.

## `src` modules (18)

| Module | Looked for | Verdict |
| --- | --- | --- |
| `index.ts` (34) | wiring, hidden hooks | No defect. `_goalCore` is a documented read-only test hook. |
| `paths.ts` (76) | path safety | No defect. `safeGoalId` escapes through `safeFileName`, strips `%`, caps at 96, falls back to `goal`; `isInside` requires a separator boundary, so a sibling prefix cannot pass. |
| `record.ts` (231) | normalization, forward compatibility | Fixed: the objective is no longer silently sliced at 4000 (the `slice` at `record.ts:140` is gone). Unknown fields validate; an unknown phase reads as `idle`; a newer version is refused. |
| `ledger.ts` (250) | paging, parsing | No defect. Every read is paged by byte offset; all three `JSON.parse` sites are guarded; a record that parses but is not a known event is reported as a diagnostic instead of dropped. |
| `store.ts` (522) | the single writer, filesystem safety | Fixed: the research focus is recorded whole (the silent 200-character cut at `store.ts:227` is gone). `O_NOFOLLOW` reads, symlink and parent rejection, atomic tmp+rename, `mode: 0o700`. |
| `scheduler.ts` (548) | arm/claim separation | No defect. Generation and dispatch are re-validated under the lock; the three error classes are thrown on the exact mismatches. |
| `prompt.ts` (226) | what reaches a model unescaped | Fixed: `verificationContractBlock` now escapes the contract and wraps it in `<untrusted_contract>`. It interpolated the contract raw, which contradicted AGENTS.md's "escape every interpolated payload". The objective block already escaped. |
| `research.ts` (122) | grant, bounds, failure path | No defect. Read-only grant with no shell; the cut states itself; a failure returns an error instead of throwing. |
| `evidence.ts` (212) | bounds, redaction | No defect. 3000/1000/200 with a `truncated` flag; `redact` is documented as not generic secret detection. |
| `check.ts` (202) | the check's own bounds | Fixed: the objective and the claim are bounded with the cut stated; a marker-less answer is an error rather than a countable refusal; a silent child names the model. |
| `core.ts` (723) | swallowed errors, silent cuts | Fixed: the check report's cut is stated (`boundCheckReport`) and the false "kept whole" comment corrected; the one rationale-free catch at `core.ts:540` now explains itself. |
| `tools.ts` (535) | schema, rendering, comments | Fixed: markdown threading, no character counts, `supersedes`, and two corrected comments (a claim about a tool-surface test that does not exist, and a goal-id comment misfiled inside `bounded`). |
| `events.ts` (245) | lifecycle ordering, swallows | No defect. Handler order is documented and no handler swallows an error. |
| `dashboard.ts` (66) | the status row | Fixed: the row carries no `[goal]` tag in any state, and never prints the goal id. |
| `commands.ts` (109) | argument parsing | No defect. Exact argument matching, so "clear my schedule" stays an objective. |
| `settings.ts` (109) | layering, bad input | No defect. Global then project then environment, sanitized per field; an unreadable file is treated as absent. |
| `live-context.ts` (182) | retention, overflow | No defect. Retention and anchor bounds are documented with the cost of exceeding them; overflow resets instead of degrading. |
| `procedure.ts` (54) | one row, host support | No defect. Verbatim subject block; the renderer registers only when the host has `registerMessageRenderer`. |

## Documented surfaces (4)

- `AGENTS.md` — updated for the row shape, the model rule, the caps, and the escaping rule.
- `README.md` — updated for the same.
- `features/goal.feature` — updated for the research row, the result row, the caps, the model fallback, and the supersede route.
- `features/monitor-evidence.feature` — unchanged; its bounds still match the code.

## Judged not defects, with the reason

- 25 exports whose only reader is their own module: `test_no_export_lacks_a_reader` deliberately counts the declaring module as a consumer.
- Four truncation helpers with different cut markers (`prompt.ts` retrieve hint, `research.ts`, `check.ts` record note, `tools.ts` band): the markers differ by context and each states its cut, so merging them would lose the recovery each one carries.
- The four remaining swallowed catches (`core.ts:103`, `store.ts:450`, `store.ts:466`, `tools.ts:517`): each has a rationale, and swallowing is correct for a lost notification, a lost lock race, and a progress update.

## Known boundary, recorded rather than left open

The completed research row is not painted by pi's TUI. Measured: the raw pty stream never contains `Research ready`, and the non-streamed `create_goal` result row never appears either, while pi's own `updateDisplay` refills the row container on every `updateResult` (`modes/interactive/components/tool-execution.js:224`, `:258`). The package's renderer output is correct — invoking the registered tool's own `renderResult` yields `[goal] Research ready · to expand` and then the markdown `Findings`.

Resolution: `get_goal(section="research")` is the reading path for findings (same markdown spec, no character count), and finalizing extension tool rows in the TUI needs a pi-side fix.