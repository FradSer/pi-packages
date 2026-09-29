# 0006: Judgment observes in shadow mode and receives a projection

## Status

Accepted. Scope: the decision-model surface in
`packages/continual-learning`. Does not change the generative planner, the
parent-owned validation and mutation boundary, or the deterministic Harness
execution gates.

## Context

The incremental Memory Selector spends a full agent process on a bounded,
closed-answer question: which existing Memory entries apply, and whether the
task warrants a Memory, Harness, or AGENTS.md change. It reads the whole Task
Slice — up to 512 KB — and its answer is a single JSON object the parent then
defends against defensively, because a generative model can emit malformed
JSON, echoed input fields, wrong casing, or duplicate filenames.

A decision model returns typed answers and probabilities for exactly this
shape of question at a small fraction of the cost. Replacing the selector
outright would be the obvious move, and it is the wrong first move for two
reasons.

First, nothing measures the selector. No record exists of which entries it
picks or how a different decision surface would differ, so there is no basis
for choosing a threshold, and no way to tell an improvement from a change in
variance. The package already records receipts for what it *wrote*; it records
nothing about what it *decided*.

Second, and more seriously: the Task Slice is verbatim user text and tool
output, which this package already treats as untrusted evidence rather than
instructions. `prompts/planner-system.md` exists precisely to say so, and the
package refuses to let retrieved Memory or quoted tool results become
instruction authority. A decision model does not treat request content as
hostile by default — content written to steer the answer can move it. Sending
the raw Task Slice to one would open an injection surface that the rest of this
package is specifically built to close. Memory descriptions make it worse over
time, because they are written by earlier runs of the same pipeline: the
corpus is a self-injection surface that grows every session.

## Decision

- A Judgment surface is a per-run reasoning surface returning bounded typed
  answers and probabilities. It never authors Memory, Harness, or instruction
  content. The request builder admits only decision question types, so a
  generative answer is unrepresentable rather than discouraged.
- Judgment ships **inactive**. It activates only when an API key resolves from
  the environment or from the persistent package configuration. Absent key,
  unreadable file, malformed JSON, unknown fields, or a configuration without a
  key all leave it inactive, and an inactive run is identical to a run without
  the feature.
- The first increment runs in **shadow mode**. The selector's decision is the
  one that reaches the parent, always. Judgment exists to produce a comparable
  record. Nothing it returns is ever written to Memory, Harness, or AGENTS.md.
- Judgment receives a **projection**: a bounded, code-derived view of observed
  state — clipped request text, the regex-classified harness event summaries,
  repository-relative touched paths, and Memory metadata. Raw tool-result
  content is never sent. Content inside a projection is inert data by
  construction, not by instruction.
- Candidates are named by **opaque, index-derived identifiers**. The parent
  maps identifiers back to filenames. A judgment answer therefore cannot
  introduce an invalid name, wrong casing, or a duplicate — those classes leave
  parent-side validation rather than gaining checks.
- Selection rules move out of instructions and into code. "Minimum sufficient
  scope" becomes a comparison the parent performs; "no arbitrary count cap",
  "exclude merely adjacent entries", and "a missing index entry does not prove
  absence" become explicit positive and negative criteria on each question.
- An **observation record** stores the run's context digest, the model version
  that answered, each judgment's identifier, value and confidence, the
  selector's own answer, and the agreement outcome. It stores no request text
  and no tool output, and is written beneath the private agent directory, per
  project, and **outside both Memory roots**: a Memory root admits only regular
  `.md` children, so a sibling log there fails consolidation's privacy
  validation and aborts the run. The log is capped and rotated.
- Judgment failures — refused connection, throttling, timeout, malformed
  answer, cancellation — are recorded and otherwise inert. An observer failing
  must not stop the observed work.
- The model is pinned to an explicit version identifier rather than a moving
  alias, and the answering version is recorded, so a threshold tuned against
  one version is not silently applied to another.
- **Promotion to authority is measured.** Committed adversarial and agreement
  fixtures gate the package tests, and promotion additionally requires an
  agreement rate and an injection-resistance rate read from observations. No
  threshold is guessed in code.

## Verification contract

Assert the boundary, not the model. Containment fixtures assert that embedded
instructions in the Task Slice and in Memory descriptions are carried as inert
data and that no code path promotes them; they do not assert that the service
resists them, which would be flaky by construction. Activation fixtures assert
that no configuration means no request and no record, and that every
fault condition fails closed. Shadow fixtures assert that the selector's
selection is what reaches the parent even when the two disagree, and that the
observation carries the disagreement. Robustness fixtures drive a refused,
throttled, and malformed endpoint over a loopback server and assert the run is
unchanged. The observation record is asserted to contain digests, values, and
agreement, and to contain no request text and no tool output.

## Consequences

The increment produces no behavior change, which is the point: it makes the
decision surface measurable before anything depends on it. The cost is an
extra network call per judged run while the feature is active, and a
projection that is a subset of what the selector sees, so the two surfaces
answer slightly different questions and their agreement rate is a lower bound
on the real one. Recording digests rather than content is what makes the
observation log safe to persist, and it is why the log cannot be replayed to
reconstruct what a user asked.
