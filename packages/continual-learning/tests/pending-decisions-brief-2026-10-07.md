# Pending decisions brief (2026-10-07)

Two policy decisions block further quality work. Both need the user. Neither was
applied. This brief states the measured evidence, the exact code a change would
touch, the risk, and the test plan for each option.

## Retained real-run hold classes, measured offline

Every on-arm memory judgment in the recorded DeepSeek cohort
(`~/.cache/pi-continual-learning/docker/20261007T014740Z`):

| Arm | Memory judgments | Outcomes |
| --- | --- | --- |
| humanize-on | 1 | decided, supported |
| referencing-on | 1 | decided, supported |
| yocto-queue-on | 3 | 2 decided supported, 1 propose with `counterevidence` uncertainty on the description |

So five of six real memory judgments were supported and applied. The single real
hold was **counterevidence on the description**, not the support class that the
fixed-sample study isolates. That is an honest distinction: the support class has
fixed-sample evidence only (8 of 8 held) and no retained real-project instance
yet.

## Decision A: the privacy preflight false positive

**Question.** Should the sensitive-material preflight stop refusing a whole Jev
review because a tracked project file contains a credential-shaped placeholder?

**Measured evidence.** 2 of 123 retained evidence entries trip the guard; both are
one `passwd:`-style placeholder inside a `toolResult` from iniconfig's own source;
both iniconfig reviews (memory and harness) were refused with zero requests, so
both Memory and Harness learning were lost on that arm.

**Exact sites.**

- `extensions/jev-learning.ts:400-415` — `sensitiveValue`, including the
  key-based rule.
- `extensions/consolidation-run.ts` — `SENSITIVE_MEMORY_PATTERNS` and
  `containsSensitiveMemoryMaterial` (the `assigned-credential` pattern matched).
- Preflight call sites in the memory, relations, readiness, and harness paths.

**Risk.** Narrowing a privacy guard can send a real secret to a third-party
model. The guard is the only thing standing between evidence text and an external
request.

**Test plan if approved.** RED: a `toolResult` that contains a placeholder
assignment from tracked source must not refuse the review, while a genuine
provider-format secret must still refuse it. GREEN: scope the guard input so
tracked-source tool output is excluded from the credential-shape rule while
user-stated and Memory-body text keeps the full rule. Then rerun one untuned
project under a new protocol.

## Decision B: the support gate for a verified observation

**Question.** Should a verified tool observation count as support for a command
fact, so a grounded supplement is not held as uncertain?

**Measured evidence.** 8 of 8 fixed samples, across three phrasings, two
languages, and with and without existing Memory, were held with
`support: uncertain`. The question's own criteria already say
`grounded: Every claim is established by the user's statement or verified
observation`. In a real run the same class would trigger one bounded semantic
repair (`extensions/inject-memory.ts:1611`, gated on `uncertain` and
`unsupported`), whose recovery is not measured.

**Exact sites.**

- `extensions/jev-learning.ts:13-15` — `YES = 0.9` and `CONFIDENCE = 0.8`.
- `extensions/jev-learning.ts:924-960` — every branch that turns an answer into
  `uncertain`, including the support check.
- `extensions/jev-learning.ts:775-780` — the support criteria text.
- `extensions/inject-memory.ts:1611` — the repair gate.

**Risk.** Lowering a threshold raises false allows. At the current gate the study
produced 0 false allows on ten negative cases; a softer gate would put that at
risk. Tightening the criteria instead would not.

**Test plan if approved.** RED: a candidate grounded in a verified tool
observation is allowed, while the speculation, transient-failure, duplicate,
conflict, and scope-expansion samples still hold. GREEN: either restate the
support criteria so a verified observation is unambiguous, or adjust the gate for
this dimension only, then re-measure on a new frozen corpus.

**Lower-risk variant worth stating.** Keep both thresholds and change only the
support criteria wording, so no false-allow rate can move. The fixed-sample
evidence cannot yet distinguish a wording problem from a threshold problem,
because a held judgment returns no answer detail. A production diagnostic that
records the controlled choice and its probability for a held dimension would
settle it, and that diagnostic change is itself a decision.

## Recommendation

Neither change should be made without your approval. If you approve neither, the
honest outcome is that the composed and independent strategies stay default-off
and the goal stays unproven with the support class and the preflight refusal named
as the reasons.