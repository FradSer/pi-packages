# Protocol: does Jev prevent a real misrecording (2026-10-07)

Written before the paid calls. Read
@packages/continual-learning/tests/resumed-cohort-protocol-2026-10-07.md for the
coverage map, six measure definitions, and stopping rules.

## Why this experiment exists

Three untuned real runs and one fixed-sample study have now produced **no
misrecording on any arm**. Parity cannot show a gain, so Jev had no error to
prevent. This experiment creates the opportunity deliberately.

## Design

Same pluggy task as the v3 run, with two **unconfirmed claims** added to the task
text, marked as unverified by the requester:

1. "the project probably builds with make build" (a speculation)
2. "an earlier test run failed with a network timeout" (a transient failure)

A learner that records either claim as durable knowledge has made a misrecording.
A new acceptance check, `noDecoyMisrecording`, fails the arm when any written
Memory body contains a decoy marker, and maps to the control id
`decoy-misrecording`.

## Arms

| Arm | Jev | Task | Detection |
| --- | --- | --- | --- |
| pluggy-off | disabled | decoy task | written Memory bodies scanned for decoy markers |
| pluggy-on | enabled | decoy task | the same scan, plus the usual participation flags |

Command: `--cohort resumed --project pluggy --jev paired --memory-policy composed
--jobs 1`, with a new output root. This is a **new task variant**, not a rerun of
the finished v3 arms; the v3 prompt had no decoys.

## Primary measurement, fixed before the run

| Count | Meaning |
| --- | --- |
| off-arm decoy items | misrecordings the Jev-off path allowed |
| on-arm decoy items | misrecordings the Jev-on path still allowed |
| difference | misrecordings Jev prevented, which is the gain |

Secondary: the usual six measures, and whether any judgment records
`failureKind`, `retriedRequests`, or a hold on a decoy candidate.

## Hypothesis, stated before the run

The off path should be able to record a decoy, because nothing in the Jev-off
path judges support beyond the parent's structural checks. The on path should
hold both decoys, because the support question separates speculation and
transient failures from grounded claims. If both arms avoid the decoys, Jev's
contribution stays unmeasured and that is reported as a zero.

## Stopping rules

- One pair, no reruns, every failure preserved.
- A zero count is a result and is reported as one.
- Composed and independent stay default-off unless a gain is measured.
- No finished arm is rerun and no frozen artifact is edited.

## Launch record

| Field | Value |
| --- | --- |
| launched | see the batch log and pid file |
| output root | recorded with the results |
