# 0012: Import project-shared Memory instead of deleting it during normalization

## Status

Accepted 2026-11-04 after a third recurrence of the same data loss. Supersedes
no earlier ADR. No learning threshold, semantic gate, privacy rule, mutation
authority or evidence-bound value changed.

## Context

`normalizeMirrorDrift` ran inside `createConsolidationRun`, before any learning
plan, receipt, rollback or `/consolidate` delete validation. Its public-file
loop removed any project-shared `.md` that had no canonical private-root copy,
treating it as an "orphan". The function's own comment says the opposite:
updates arriving through the git-tracked mirror land in public first, so either
side can be the fresh one.

A project whose `.memory/` mirror holds git-tracked entries absent from the
private root therefore lost every such entry on each learning run. Local
history recorded four `applied` memory changes with seven `public/<name>.md`
targets whose successor was `null`: 2026-10-12, and three times on 2026-11-03.
`learn_current_memory` still reported `no durable changes`, because the
deletion happened before the pipeline's attempts; the user had to restore the
files from HEAD three times. The deletion also bypassed the parent-owned
`/consolidate` delete contract (verified staleness verdict, non-empty
`preservedIn`, preservation, privacy, rollback and receipts).

`normalizeTrackedMemory` wrapped that normalization in
`recordLearningMutation`, which is why the deletions appeared as legitimate
`applied` history changes with an empty successor.

## Decision

- A project-shared entry with no private-root copy is imported byte-identically
  into the private root and reported as a `public-to-harness` repair. It is
  never deleted during normalization.
- Only a harness-only file leaked into the shared mirror is removed. That is a
  privacy-boundary repair; the canonical copy remains in the private root.
- Pre-run normalization never deletes a project-shared Memory entry. Deletion
  of a Memory entry stays exclusively inside the parent-owned `/consolidate`
  transaction with its existing verdict, preservation, rollback, receipt and
  privacy gates.
- The agent-triggered tool result reports the number of imported entries and
  states that no project-shared Memory was deleted. `normalizedImports` is
  included in the result details. A pipeline that learned nothing no longer
  looks like a silent no-change run when normalization imported tracked files.
- Existing historical records that contain `after: null` are retained as
  evidence, not rewritten or relabelled.

## Alternatives considered

| Alternative | Rejected because |
| --- | --- |
| Keep removing orphans but log the removal | A reported deletion is still a deletion outside the transaction; the user's data is gone and the receipt still undercounts it. |
| Fail closed when a public-only file exists | It would make every fresh clone with a git-tracked mirror unrunnable until manual repair, repeating the pre-normalization failure mode. |
| Import only files tracked by git | Normalization must not depend on a subprocess or on git state for a privacy boundary; the existing absent-private-root branch already imports every shared file. |
| Rewrite the four historical `after: null` records to hide the deletion | Historical evidence is immutable; rewriting it would remove the proof of the defect. |
| Move deletion into the learning plan so the receipt records it | Deleting user Memory without a validated staleness verdict and `preservedIn` is forbidden regardless of where it is recorded. |

## Verification contract

- `tests/mirror-import.test.ts`: seven tracked public-only entries survive, are
  imported byte-identically, appear in both indexes, produce no `removed`
  entries, and produce no `after: null` change in learning history through
  `normalizeTrackedMemory`; a harness-only leak is still removed.
- `tests/test_memory_security.py::test_mirror_drift_is_normalized_before_the_run`
  carries the updated drift contract: a public-only entry is imported, only the
  harness-only leak is removed.
- `features/consolidate.feature` and
  `features/learning-state-integrity.feature` carry the scenarios.
- A real `pi --print` CLI loop with the deterministic provider reproduces the
  exact defect when the fix is reverted (seven shared files gone, seven
  `public/...` deletions in history, receipt still `memory:applied`) and passes
  with the fix (all seven present, all seven imported, zero deletions).
- A second real-CLI loop calls `learn_current_memory` and asserts the tool
  result reports the imports with `Learning 1 memory applied` and no
  `finished with issues`.

## Consequences

A fresh clone whose private root lacks git-tracked shared entries now gains
canonical copies on the first learning run instead of losing the shared ones.
Both indexes are regenerated to include them, so final privacy/mirror
validation still holds. Historical records with `after: null` remain visible;
they describe the earlier defect, not the current behaviour. Undoing one of
those old records would restore bytes that are already present, so no new
migration of history is required.
