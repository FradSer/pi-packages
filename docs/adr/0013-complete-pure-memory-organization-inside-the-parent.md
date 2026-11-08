# 0013: Complete pure Memory organization inside the parent

## Status

Accepted 2026-11-04. Supersedes no earlier ADR. No learning threshold, semantic
gate, privacy rule, mutation authority or evidence-bound value changed.

## Context

An agent-requested `learn_current_memory` turn whose frozen task slice held no
durable knowledge still routed Memory to the full pipeline. The parent floored
`screen.memory = true` for the explicit request, then started a selector child
and a Memory planner child using a separate learning model. A 226-entry session
with eight omitted evidence entries downgraded the policy to `propose`; the
planner ran for 2m 14s over 414,113 input tokens at `$0.1547` and produced
zero operations, yet the receipt reported `proposed` and "Memory proposals saved
for review" — a result that required an external actor to act on afterward.

Two further observability defects were visible in the same receipts. Evidence
reasons such as `no-harness-evidence` were left in place when the phase was
actually disabled by the agent-requested Memory-only policy, so the label gave
the wrong cause. `input.entryCount` counted the whole session (839, 226) while
the evidence screen examined only the small frozen current-task slice (2), and
the receipt exposed no screened count. A zero-operation `proposed` attempt was
reported as a saved proposal even though nothing was pending.

The user's requirement was that the Memory task finish entirely inside the
plugin, with no feedback to an external agent followed by further external
action.

## Decision

- Keep `learn_current_memory`. An explicit request whose frozen task slice has
  no user-stated durable knowledge completes in the parent: it normalizes
  mirror drift, rebuilds both indexes, removes empty learning scope
  directories, writes one zero-cost `memory: noop` attempt and returns an
  explicit completed result. No selector, planner or review worker starts and
  no proposal is saved.
- A task containing durable user knowledge still runs the original learning
  pipeline and can really write Memory and Harness changes. Credential-shaped
  frozen evidence and an invalid learning model keep their fail-closed paths;
  the in-process branch refuses to run for either.
- `LearningScreen.reasons` describes evidence from the frozen slice only.
  `LearningScreen.routing` records policies and explicit requests. A phase
  disabled by policy is named as such, not as absent evidence.
- `LearningInputSource.entryCount` remains the input size; the new optional
  `screenedEntryCount` is the frozen slice size actually screened. The receipt
  validator accepts both new optional fields.
- A `proposed` attempt with zero operations and zero pending operations is no
  longer reported as "proposals saved for review". A real proposal with
  operations still is.

## Alternatives considered

| Alternative | Rejected because |
| --- | --- |
| Keep the full pipeline and only fix the summary wording | It still spawns two external workers, spends minutes and money, and leaves a proposed outcome for a request with nothing to learn. |
| Never start planner children for any request | It would remove the validated path that really generates Memory and Harness from durable knowledge, which the user explicitly kept. |
| Drop `learn_current_memory` in favour of purely automatic learning | The user required the tool to stay, and the explicit request is what distinguishes organization from knowledge capture. |
| Rename the three evidence reason strings globally | Historical receipts and cohort fixtures retain those strings; changing the pure function output would relabel immutable evidence. Separating routing into its own field fixes the attribution without rewriting history. |
| Put `screenedEntryCount` on the screen instead of the input | `entryCount` already lives on `input`; the two counts belong together and replay source binding only reads a fixed field subset. |

## Verification contract

- `tests/memory-receipt-truth.test.ts` covers screened counts, evidence/routing
  separation, and zero-operation proposed wording, including the positive case
  that a real proposal is still reported.
- `tests/test_learning_controls.py::test_pure_organize_request_completes_in_process_without_workers`
  drives the real policy harness: zero selectors, zero planners, no proposed
  history, `status: organized`, a receipt with `organized-in-process` routing
  and `screenedEntryCount`.
- A real `pi --print` CLI loop calls the tool in disposable roots. The pure
  organize turn returns `worker_responses: []`, the explicit in-process text,
  `screenedEntryCount: 2`, `memory: noop` with zero operations and no
  proposals. The durable-knowledge turn still returns `memory: applied` with
  one operation and physically writes `loopback_memory_fact.md` plus the index.
- Checks at acceptance: extension TypeScript project clean, package Bun tests,
  full Python suite against the recorded baseline, and packed-manifest check.

## Consequences

Pure organization is now free, immediate and self-contained. Historical
receipts keep their old reason strings and remain valid under the optional
fields. The `organized` tool status is a new value that callers may need to
recognize; unknown statuses were already handled as non-failures. A task whose
durable knowledge lives outside the frozen current-task slice is still routed
to the learning pipeline by its own evidence, not by this branch.
