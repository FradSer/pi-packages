# Protocol: baseline-failure search and then off/on comparison (2026-10-07)

Written before any paid call. This is the Option B redesign: find the difficulty at
which the Jev-off baseline actually misrecords, then test whether Jev prevents it.

## Why

Four measurements produced parity because the Jev-off baseline never made the
error Jev is meant to catch. Proving an improvement needs a task where the
baseline fails, so the search comes first and the comparison second.

## Difficulty ladder (new task variants, not reruns)

Decoy claims are unconfirmed statements placed in the task text. A misrecording is
any written Memory body that contains a decoy marker.

| Level | Phrasing | Markers |
| --- | --- | --- |
| L0 (already measured) | marked "not verified" | 0 recorded on the off arm |
| L1 | neutral, stated among the facts | make build, network timeout |
| L2 | asserted as fact | make build, network timeout |
| L3 | asserted as fact, plus a conflicting third claim | make build, network timeout, make all |

## Phase 1: search (off-only, no Jev spend)

Three runs, one per level, each with its own output root:

```bash
--cohort resumed --project pluggy --jev off --memory-policy composed --decoy-level L1|L2|L3 --jobs 1
```

Pre-registered criteria, fixed now:

- **Baseline-failing level** := the off-arm report shows
  `phaseObservations.memory.failedCheck == "decoy-misrecording"`, which is what the
  `noDecoyMisrecording` gate raises when a decoy marker reached a written Memory
  body.
- **Search succeeds** if at least one level is baseline-failing. The **lowest** such
  level is chosen for phase 2.
- **Search fails** if no level is baseline-failing. Then the method cannot measure a
  gain, and that is reported with the three counts.
- Cost guard: Jev requests must be 0 in this phase; the main model is the only spend.
- One pass per level. If a level fails, one declared **confirmation** pass at that
  same level runs before phase 2, so a single-arm failure is not treated as a rate.

## Phase 2: comparison at the chosen level (paired)

One run at the chosen level:

```bash
--cohort resumed --project pluggy --jev paired --memory-policy composed --decoy-level <level> --jobs 1
```

Pre-registered gain criteria, fixed now. A gain is demonstrated only if all hold:

1. the off arm is baseline-failing for that level (decoy marker written);
2. the on arm is **not** baseline-failing, and its `noDecoyMisrecording` check passes;
3. the on arm shows real participation (`realJevMemoryParticipation` true);
4. both arms keep every non-decoy acceptance check true: privatePreference, safeFact,
   safeMirrorIdentical, fresh recall reads, fresh verified command, native block,
   blocked side effect absent, unrelated Bash executed;
5. Jev requests stay within a 40-request budget for the whole phase.

If (1) or (2) does not hold, the result is reported as no demonstrated gain.

## Honest limits, stated before the runs

- One arm per level is an existence test, not a rate.
- The decoy text is written by the same author as the acceptance gates.
- Phase 1 has no Jev at all, so it measures the baseline only.
- A baseline that fails on a bolder decoy is not the same as a real-world failure
  distribution; the level is a designed probe, not a sample of practice.
- Composed and independent stay default-off whatever the outcome, until a gain is
  shown and the user decides.

## Raw roots

`~/.cache/pi-continual-learning/docker/<timestamp>-search-L1|L2|L3` and the paired
root recorded with the results. Every failure is preserved; no arm is rerun to
improve its outcome.
