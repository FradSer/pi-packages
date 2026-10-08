# Assessment of the remaining steps (4 and 5) and a decision request

Steps 1 to 3 are landed and verified. Steps 4 and 5 turn out to carry a design
question that changes what the objective can claim, so they are put to you before
more code changes.

## Step 4 (stop repeating the cited support set per question): largely subsumed

The step-1 finding was that the per-question byte bound is the binding constraint
because the full cited support set rides in every review question, so the window cap
can never bind. Two facts change the picture:

- The only observed refusal came from a **degenerate citation set** (four candidates
  citing entry 0 while quoting four different entries).
- Step 2 now catches exactly that case **before any judge call** and routes it into
  the structural repair, with the locations named.

So step 4 remains necessary only for a plan whose *legitimately* large cited support
set exceeds 64 KB per question. No run has produced that. Options: (a) leave step 4
out and revisit if a real case appears, or (b) do it anyway as defensive work, with
the risk that changing what the judge sees could move the frozen corpus away from
14 of 14 and 0 false allows.

**Recommendation: (a).** Do not change the review wire without a reproduced case.

## Step 5 (harness coverage repair): real, but attribution is ambiguous

Seam, read from the source:

- `extensions/inject-memory.ts:2155` passes `semanticRepair: policies.harness === "apply"`
  into the harness consolidation **only when Jev is enabled**.
- `harness-consolidation.ts:702` records that the semantic repair "shares the single
  existing repair slot with structural recovery".
- `inject-memory.ts:2176` records the attempt as `noop` when the harness plan is valid
  and has zero operations, which is exactly what the weak-generator on arm produced
  while the task text stated a durable prohibition.

The ambiguity: whether the coverage repair is a **parent-side check** (fires on both
arms, so it is a pipeline quality fix) or a **Jev-conditional behaviour** (fires only
when Jev is enabled, because the repair slot is only opened then). The second would
make the on arm better than the off arm, but the difference would come from Jev's
*enablement* opening a repair slot, not from Jev's *judgment*, which is a weak claim
against the objective and should not be presented as Jev adding value.

**Recommendation:** implement it as a parent-side coverage check (both arms), record
it as a pipeline quality fix, and keep the objective's claim separate: Jev's judged
value rests on the fixed-sample evidence (10 of 10 negatives held, 0 false allows)
and not on this repair.

## What is already established, independent of this choice

| Item | State |
| --- | --- |
| Step 1 bounds diagnostics | landed, RED then GREEN |
| Step 2 citation legality and routing | landed, unit plus source-order tests |
| Step 3 bounds as a repair trigger | landed, weak on arm went from 0 to 2 Memory operations |
| Frozen corpus after the changes | 14 of 14 matched, 0 false allows, 0 false holds |
| Full verification | 1096 passed in 622.16s, typecheck 0, pack:check 0, dry pack ok, diff check 0 |
| Attribution caveat | the weak arms saw different plans, so Jev cannot be credited for the 0-to-2 change without the controlled comparison |

The controlled comparison is the outstanding item that would settle attribution: one
fixed plan through the Jev-off and Jev-on paths, counting what lands. It needs a seam
that can inject a fixed plan, which does not exist yet in the runner.
