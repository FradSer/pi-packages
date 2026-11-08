# Harness one-step write is blocked by the native strict wire

Phase 2 of the single-tool refactor planned to remove the `harness_preview`
two-step and move positive/negative case evaluation into the `tool_call`
write-time check. An 11-agent ultracode recon + 3 adversarial lenses
rejected the synthesized design 3:0. The decisive reason is a Pi wire
constraint, verified directly against the installed Pi 1.3.0 runtime.

## The constraint

`node_modules/@earendil-works/pi-coding-agent/dist/core/tools/write.js`
declares:

```ts
const writeSchema = Type.Object({ path: Type.String(...), content: Type.String(...) });
constrainedSampling: { type: "json_schema", strict: "prefer" }
```

On a strict-capable provider, `resolveJsonSchemaStrictSampling` calls
`makeStrictJsonSchema` -> `makeJsonSchemaNodeStrict`, which sets
`schema.required = ["path","content"]` and `schema.additionalProperties = false`.
A model honoring that wire **cannot emit a sibling `harnessCases` argument**.
`content` is an unconstrained string, so it is the only field that can carry a
case envelope. `tests/harness-write-wire.test.ts` calls the real
`getJsonSchemaToolParameters(tool, true)` and pins both facts with executable
assertions.

The offline acceptance runner `tests/live_harness_first_run.py` uses the
scripted `harness-first-fixture.ts` provider, which synthesizes `toolCall`
arguments directly and never serializes through a real provider schema.
Therefore it cannot detect a producing-side wire defect: an implementation
could be green offline and permanently rejected on a real strict provider.

## Decision for this turn

No destructive Phase-2 production edit is made. The wire constraint, the
executable contract test, the corrected feature scenario and this ADR are
delivered. Phase 1 (option B) remains green and untouched. This follows the
same rule used when Phase 1 was rejected: fix the premise and pin the facts
before writing code that could weaken a Harness gate.

## Three candidate channels (not yet chosen)

1. **Content envelope + wire proof.** Cases travel inside the `content`
   string; the parent parses and strips them in `tool_call`, rewrites
   `event.input.content` to the exact final bytes, and re-takes every
   `JSON.stringify(event.input)` snapshot (`authoringInput`,
   `inputSnapshot`, `writeApproval.input`, `recheckHarnessWriteApproval`).
   `validateRuleContainer` rejects an unknown top-level key, so the strip
   must be exact. Requires a strict-capable provider-wire acceptance test and
   a coupled rewrite of the offline fixture step budgets and pinned prompt
   literals. Smallest rewrite, highest snapshot-ordering risk.
2. **Declared parent-owned tool.** Keep the native `write` untouched; register
   one parent tool whose schema declares cases, and let it perform the full
   validated, atomic write + readback + rollback, receipt and undo. Cleanest
   wire and closes the ADR-0014 open item, but rewrites the Harness write
   path and touches the automatic consolidation path. Largest scope.
3. **Defer.** Keep the two-step `harness_preview` until a Pi version or an
   explicit decision changes the wire. Zero risk, no progress on Phase 2.

## Implementation delivered (2026-11-05)

Option 2 landed as an ADDITIVE declared tool, not a deletion of the two-step
path. `guardrails.ts` now exports `HARNESS_WRITE_PARAMETERS`
(`Type.Object({path, content, cases})`, cases required) and registers
`harness_write` with `defaultActive:false`, activated/reset with the existing
`beginHarnessAuthoring` / `resetSession` lifecycle. Its execute is self-contained:
active-authoring check, no-UI fail-closed, exact target pin, containment,
predecessor bytes, `validateHarnessWrite`, `previewHarnessCandidate`
(positive AND negative cases), confirm, TOCTOU recheck, `writeFileAtomic` +
readback, `recordLearningMutation` for undo, `buildLearningReceipt` /
`writeLearningReceipt` for a real receipt, then `finishAuthoring`. The prompt
step-4/5 now names `harness_write` while keeping every pinned literal.
The existing `harness_preview` evaluator and native `write` gate chain remain
intact and are still accepted; the offline two-step acceptance runner stays
green. `tests/harness-write-behavior.test.ts` drives the new path end to end
(registration, refusal cases, exact bytes, cases never persisted, receipt,
undo history, tool teardown); `tests/harness-write-wire.test.ts` proves strict
sampling emits `cases`. No frozen file, `harness-consolidation.ts`,
`guardrail-engine.ts`, the 9 flags or the `learning_read` marker changed.

Known limitation: the offline scripted-provider PTY runner does not exercise
the new tool's dialog on a real strict provider; the strict-wire unit tests
cover the schema transform, and a real strict-provider loopback acceptance is
still a separate piece of evidence. This delivery does not claim semantic
learning benefit or real-model acceptance.

## Invariants that any channel must keep

- Exact candidate and predecessor bytes; parent-side positive AND negative
  cases; no-UI fail-closed; `ctx.ui.confirm` and
  `ctx.ui.select(["Allow once","Block"])`; `recheckHarnessWriteApproval`
  after every await; one admitted write with one-shot consumption; no
  scratch files or second write.
- Cases never enter persisted rules: `guardrail-engine.ts` `RULE_FIELDS`,
  `ruleRevision`, `validateRuleContainer`, `validateRuleDeclaration` and
  `learnedRules` ownership stay unchanged.
- `previewHarnessRuleCases` (per-rule `{positive,negative}`, planner-child) is
  a different evaluator from `previewHarnessCandidate` (flat
  `{ruleId,input,matches}`, interactive). `guardrails.ts` importing
  `harness-consolidation.ts` closes an ESM cycle, so moving both into the
  write gate requires extracting a leaf module first. The plan's literal
  "move both" wording needs an explicit amendment if only one moves.
- No stale `harness_preview` / `previewed` / "preview again" text in prompt,
  block reasons, guidance or docs after the deletion. Pinned literal
  substrings in `test_harness_authoring_safety.py` ("use write at ...",
  "non-executing evaluator", step order) must be updated consistently.
- Frozen evidence, the 9 `--learning-*` flags, `planner-json-output.ts` and
  the `TOOL_NAMES.learningRead` marker stay byte-identical. No real-model /
  paid / `--live` runner without explicit authorization. Fresh-agent review
  after the destructive phase before Phase 3.
