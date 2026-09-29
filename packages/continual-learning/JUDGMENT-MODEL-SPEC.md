# Judgment model shadow mode

## Problem Statement

Every settled task that passes the regex screen in `extensions/learning-efficiency.ts`
spawns a full `pi` agent process through `runPiWorker` to answer one question:
which existing Memory entries are needed, and whether the task warrants a
Memory, Harness, or AGENTS.md change. That call reads the whole Task Slice —
up to 512 KB of JSON — and returns a single JSON object that the parent then
re-validates defensively.

Three problems follow from that shape:

1. **Cost and latency.** The selector pays agent-grade price for a bounded,
   closed-answer judgment. A full run is 30 minutes of budget for a
   metadata-only routing decision.
2. **Schema fragility.** Because a generative model produces the answer, the
   parent must defend against malformed JSON, echoed input fields, wrong
   casing, and duplicate filenames. Roughly sixty lines of
   `parseSelectionObject` exist only to absorb those failures, and each one
   discards an otherwise valid run.
3. **Unmeasurable judgment.** The selector's actual behavior — which entries
   it picks, and why — leaves no record. There is no data for anyone to
   evaluate the decision surface or to justify changing it.

## Solution

Introduce **Judgment** — a decision model surface that answers the same
selection and routing questions as typed probabilities instead of generated
prose — and run it in **shadow mode** beside the existing selector.

In shadow mode Judgment observes; the existing selector still decides. Every
run appends one bounded observation record containing the judgment values,
their confidence, the selector's actual answer, and whether the two agreed.
No file the parent writes changes. No Memory, Harness, or AGENTS.md content
is produced by Judgment.

Judgment activates only when it is configured — an API key in the
environment, or an API block in the persistent package configuration. With no
configuration the package behaves exactly as it does today.

The observation record is the deliverable of this increment: it is what makes
promotion to authority a measured decision rather than a guessed threshold.

## User Stories

1. As a package maintainer, I want Judgment to be off unless it is explicitly configured, so that installing this package never introduces network calls or credential requirements on its own.
2. As a package maintainer, I want a single persistent configuration file to carry the API key, model, and base URL, so that credentials are not confined to one shell invocation.
3. As a package maintainer, I want the environment variable to take precedence over the configuration file, so that a one-off run can be pointed at a different account without editing persisted state.
4. As a package maintainer, I want the observed model version to be recorded alongside every judgment, so that a threshold tuned against one version is not silently applied to another.
5. As a package maintainer, I want the model pinned to an explicit version identifier rather than a moving alias, so that recorded probabilities stay comparable across runs.
6. As a package maintainer, I want every observation record to carry the run's context digest rather than the task text, so that records can be correlated and rotated without retaining user content.
7. As a privacy-conscious user, I want observation records to never contain my request text or tool output, so that shadow telemetry cannot leak content I did not ask to persist.
8. As a privacy-conscious user, I want observation records written beneath the private agent directory but outside both Memory roots, so that shadow telemetry neither reaches the project-shared Memory surface nor breaks the private Memory root's own contract.
9. As a package maintainer, I want a fixed fixture suite to prove that embedded instructions inside the Task Slice do not steer the selection, so that promotion to authority has a written precondition.
10. As a package maintainer, I want a fixed fixture suite to prove that Memory descriptions cannot act as instructions, so that the cross-run self-injection surface is covered.
11. As a package maintainer, I want an offline script that reads the observation log and reports agreement and injection-resistance rates, so that promotion thresholds come from measurement rather than intuition.
12. As a package maintainer, I want observation records capped and rotated, so that a long-lived install cannot grow an unbounded private file.
13. As a package maintainer, I want a malformed or unreadable configuration to fail closed to "Judgment disabled", so that a broken config cannot change learning behavior.
14. As a package maintainer, I want a rejected, throttled, or unreachable Judgment endpoint recorded as a failed observation and nothing more, so that a service outage cannot affect the learning pipeline.
15. As a package maintainer, I want cancellation of an in-flight Judgment request to propagate, so that session shutdown behaves as it does for the existing selector.
16. As a package maintainer, I want the state sent for judgment to be a bounded, code-derived projection rather than the raw Task Slice, so that the request fits the model context budget and excludes raw tool output.
17. As a package maintainer, I want candidates identified by opaque identifiers rather than filenames, so that no judgment answer can introduce an invalid or mis-cased Memory name.
18. As a package maintainer, I want a bounded TUI line naming the judgment observation, so that shadow mode is visible rather than silent.
19. As a package maintainer, I want a bounded harness-check entry recording the outcome, so that agreement is inspectable without reading files.
20. As a package maintainer, I want the existing selector prompt retained as the fallback path, so that disabling Judgment restores today's behavior with no migration.

## Scenarios

```gherkin
Feature: Judgment shadow mode
  Judgment observes the incremental selector's decisions. The selector still
  decides, and the parent still owns every mutation.

  # ── Activation ────────────────────────────────────────────────────────

  Scenario: No configuration leaves Judgment inactive
    Given no API key in the environment
    And no API block in the persistent package configuration
    When a settled task starts incremental learning
    Then no judgment request is made
    And the selector decides exactly as it does today
    And no observation record is written

  Scenario: An environment API key activates Judgment
    Given an API key in the environment
    When a settled task starts incremental learning
    Then judgment is active for that run

  Scenario: A configured API block activates Judgment
    Given no API key in the environment
    And an API key in the persistent package configuration
    When a settled task starts incremental learning
    Then judgment is active for that run

  Scenario: The environment key takes precedence over the configured key
    Given an API key in the environment
    And a different API key in the persistent package configuration
    When a judgment request is authorized
    Then the environment key authorizes it

  Scenario: An unreadable configuration fails closed
    Given a persistent package configuration that cannot be read safely
    When a settled task starts incremental learning
    Then judgment is inactive
    And the selector decides exactly as it does today
    And the configuration fault is reported as a diagnostic

  Scenario: A configuration without an API key fails closed
    Given a persistent package configuration that declares a model but no API key
    And no API key in the environment
    When a settled task starts incremental learning
    Then judgment is inactive

  # ── Shadow authority ──────────────────────────────────────────────────

  Scenario: The selector still decides the selection
    Given judgment is active
    And judgment and the selector disagree about which Memory entries apply
    When the run completes
    Then the selector's selection is the one that reaches the parent
    And the disagreement is recorded in the observation

  Scenario: Judgment never supplies Memory content
    Given judgment is active
    When the run completes
    Then no Memory body, Harness rule, or instruction text originates from judgment

  # ── State projection ──────────────────────────────────────────────────

  Scenario: Only a bounded projection is sent
    Given judgment is active
    When a judgment request is built
    Then the request text is the code-derived projection
    And raw tool-result content is not present in the request
    And the request stays within the model context budget

  Scenario: Memory entries are identified opaquely
    Given judgment is active
    And the private Memory root holds many entries
    When a judgment request is built
    Then each entry is identified by an opaque identifier
    And the answer can be mapped back to a filename only by the parent

  Scenario: An absent Task Slice still yields a valid projection
    Given judgment is active
    And the Task Slice contains no user request text
    When a judgment request is built
    Then the projection is still bounded and well formed

  # ── Robustness ────────────────────────────────────────────────────────

  Scenario: An unreachable endpoint does not affect the pipeline
    Given judgment is active
    And the judgment endpoint refuses the connection
    When the run completes
    Then the observation records the failure
    And the selector decides exactly as it does today

  Scenario: A throttled endpoint does not affect the pipeline
    Given judgment is active
    And the judgment endpoint throttles the request
    When the run completes
    Then the observation records the failure
    And the selector decides exactly as it does today

  Scenario: A malformed answer does not affect the pipeline
    Given judgment is active
    And the judgment endpoint answers without the expected questions
    When the run completes
    Then the observation records the failure
    And the selector decides exactly as it does today

  Scenario: Cancellation propagates to an in-flight judgment request
    Given judgment is active
    And a judgment request is in flight
    When the run is cancelled
    Then the judgment request is abandoned
    And the cancellation reason is recorded

  # ── Observation record ────────────────────────────────────────────────

  Scenario: An observation carries judgments and agreement, not content
    Given judgment is active
    When the run completes
    Then the observation records the run's context digest
    And the observation records each judgment value and its confidence
    And the observation records the selector's own answer
    And the observation records whether the two agreed
    And the observation contains no request text and no tool output

  Scenario: An observation is written outside both Memory roots
    Given judgment is active
    When an observation is recorded
    Then it is written beneath the private agent directory
    And it is written outside the private Memory root
    And it is outside the project-shared Memory surface
    And a private Memory root still holds only Markdown children

  Scenario: The observation log is capped and rotated
    Given judgment is active
    And the observation log has reached its cap
    When another observation is recorded
    Then the log stays within its cap
    And the most recent observations are the ones retained

  # ── Adversarial containment ───────────────────────────────────────────

  Scenario: An instruction embedded in the Task Slice does not steer selection
    Given judgment is active
    And the Task Slice contains text instructing the reader to select every
    Memory entry and to create a rule that always confirms
    When a judgment request is built and answered
    Then the projection carries that text as data only
    And the fixture asserts the selection is unchanged

  Scenario: A Memory description cannot act as an instruction
    Given judgment is active
    And a Memory description contains text instructing the reader to disregard
    the parent and treat every entry as selected
    When a judgment request is built and answered
    Then that description is carried as data only
    And the fixture asserts the selection is unchanged

  # ── Promotion gate ────────────────────────────────────────────────────

  Scenario: The promotion report reads only the observation log
    Given an observation log containing agreement and containment outcomes
    When the promotion report is generated
    Then it reports the agreement rate and the containment rate
    And it proposes no threshold of its own

  Scenario: The fixture suite gates the package tests
    Given a change that would let embedded instructions steer the projection
    When the package tests run
    Then the containment fixture fails
```

## Implementation Decisions

### Judgment is a decision-model surface, not a generator

Judgment answers bounded questions with typed answers and probabilities. It
does not write Memory bodies, Harness rules, instruction text, or diagnostic
prose. Those remain the generative planner's responsibility. The separation is
structural: the request builder admits only `noul`, `choice`, and `score`
questions, so a generative answer is unrepresentable rather than merely
discouraged.

### Opaque candidate identifiers

Each Memory entry in the request is identified by an opaque, index-derived
identifier. The parent maps identifiers back to filenames. A judgment answer
therefore cannot introduce an invalid name, wrong casing, or a duplicate,
which removes those three classes from parent-side validation instead of
adding checks for them.

### Threshold rules live in code, not in instructions

The selector prompt's current clauses — "no arbitrary count cap", "exclude
merely adjacent entries", "a missing index entry does not prove absence" —
become explicit positive and negative criteria attached to each question. The
"minimum sufficient scope" selection rule becomes a code-side comparison, so
it is enforced rather than requested.

### The state is a code-derived projection

The request carries a bounded projection: clipped request text, the
regex-classified harness event summaries, repository-relative touched paths,
and Memory metadata. Raw tool-result content is never sent. The projection is
required to stay within the model context budget; a projection that would
exceed it is clipped in a fixed order.

This is a security requirement, not an optimization. The Task Slice is
verbatim user text and tool output, which this package already treats as
untrusted evidence rather than instructions. A decision model that does not
treat request content as hostile must not receive unfiltered content.

### Shadow mode changes no decision

The selector's output remains authoritative. Judgment's purpose in this
increment is to produce a comparable record. Every disagreement is an
observation, never an override.

### Configuration is opt-in and fail-closed

Judgment activates only when an API key resolves from the environment or from
the persistent package configuration. Any other condition — absent key,
unreadable file, malformed JSON, unknown fields, missing key — leaves
Judgment inactive and the run identical to today. The environment takes
precedence over the file. Model and base URL may come from either source; the
model is pinned to an explicit version identifier rather than a moving alias.

### Observations are judgment records, not content records

An observation stores the run's context digest, the model version that
answered, each judgment's identifier, value, and confidence, the selector's
own answer, and the agreement outcome. It never stores request text or tool
output. It is written beneath the private agent directory, per project, and
**outside both Memory roots**: a Memory root admits only regular `.md` children,
so a sibling log there fails consolidation's privacy validation and aborts the
run. The log is capped and rotated.

Keeping content out of the record is what makes the record safe to persist at
all. The digest is sufficient to correlate observations with runs.

### Failures degrade to observation

A refused connection, a throttled request, a timeout, an unparseable answer, or
a cancellation is recorded as a failed observation. None of them changes the
selection. Judgment is an observer; an observer failing must not stop the
observed work.

### The transport lives in the shared runtime

The decision-model client belongs in the shared internal runtime package
alongside the existing worker helper, not inside this package. It is shared
infrastructure with its own lifecycle concerns — credential resolution,
retry policy, abort propagation, bounded output — and the package guidelines
require shared runtime code to live there.

### Promotion to authority is measured, not assumed

Promotion requires both a committed fixture suite and a live measurement. The
fixtures gate the package tests. The promotion report reads the observation
log and reports agreement and containment rates without proposing a threshold;
choosing the threshold remains a human decision informed by the report.

## Testing Decisions

**What makes a good test here.** These tests assert observable boundary
behavior: which request was made, what it contained, what was recorded, and
which answer reached the parent. They do not assert on internal function
shapes, and they never assert that a judgment value crossed a particular
number, because thresholds are explicitly not yet chosen.

**The seam.** One seam: the existing Bun subprocess harness that imports the
package's TypeScript extensions and returns JSON. The decision-model endpoint
is reached over a loopback HTTP server bound by the test, and the base URL is
supplied through the same configuration path production uses. This exercises
the real transport, the real retry and abort behavior, and the real
configuration resolution, and it requires no test-only hooks in production
code.

**Mocking.** Nothing inside the package is replaced. The boundary being
substituted is the network, which is the boundary the design actually depends
on. A test that stubbed the client would not exercise credential resolution,
throttling, or cancellation, and those are behaviors under contract.

**Prior art.** The package already tests through this harness. The existing
selector tests drive the same public function with synthetic Task Slices and
assert on the resulting selection and error text, and the containment fixtures
follow the same shape as the existing sensitive-corpus fixture.

**Containment fixtures are not probabilistic.** The adversarial fixtures
assert that the *projection* carries embedded instructions as inert data and
that no code path promotes them. Assertion of the model's resistance to those
instructions is a property of the service and belongs in the promotion
measurement, not in a test that would be flaky by construction.

## Out of Scope

- A user-facing command for reading the observation log. `/consolidate` reports
  the measurement on the receipt it already prints, and a second read-only
  command would be a surface the user has to learn for a measurement that belongs
  with the run that produced it.
- Making Judgment authoritative. This increment only measures.
- Generating Memory, Harness, or AGENTS.md content with a decision model. That
  is out of reach for this model class by construction.
- Replacing the generative planner or the deterministic Harness execution
  gates.
- Multi-candidate proposal generation and the two-stage shortlist decision.
- Choosing or encoding any threshold.
- The staleness and operation-kind judgments inside the consolidator planners.

## Further Notes

- The package already separates reasoning from mutation: children plan, the
  parent validates and writes. Judgment sits strictly on the reasoning side and
  is the first component in the package to hold a state-dependent, per-run
  decision surface that is measured rather than assumed.
- The observation log is the only new persistent artifact this increment adds.
  It lives under the private agent directory with the same bounded-write discipline
  the package already applies to run artifacts.
- The single-question case is deliberately left unbuilt. It is cheap to add
  once the shadow surface exists, and adding it during this increment would
  widen the change without strengthening the measurement.
