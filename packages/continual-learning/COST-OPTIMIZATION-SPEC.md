# Incremental continual-learning consolidation

## Problem Statement

The default continual-learning pipeline treats one completed task as a reason to re-audit the complete session and complete Memory corpus. On a large project, one manual consolidation captured 1,368 session entries and a 3.66 MB snapshot; two Memory attempts reported 2,498,575 total tokens, including 137,863 input, 35,208 output, and 2,325,504 cache-read tokens, while applying zero operations. The default behavior therefore spends substantial time and provider capacity rediscovering historical context and restating unchanged Memory.

## Solution

Default automatic learning and `/consolidate` become incremental. They operate on the current completed task slice, use a lightweight model selection pass over the Memory index and descriptions to choose related existing Memory, and send only those selected bodies plus current-task evidence to small delta planners. Harness and AGENTS.md reuse the same authoritative dossier instead of exploring the complete snapshot or repository independently. Planner output contains only proposed changes; the parent derives unchanged inventory, validation state, and receipts mechanically. `/consolidate full` remains the explicit full-corpus maintenance path.

## User Stories

1. As a user, I want routine learning to inspect only the task that just completed, so that long sessions do not make every later learning run more expensive.
2. As a user, I want `/consolidate` to be incremental by default, so that an explicit cleanup command does not automatically re-audit the entire Memory corpus.
3. As a user, I want `/consolidate full` to remain available, so that I can deliberately request full-corpus maintenance.
4. As a user, I want a lightweight model to select related Memory from bounded metadata, so that relevance remains semantic without reading every Memory body.
5. As a user, I do not want an arbitrary fixed candidate-count limit, so that the selector may choose every genuinely related Memory.
6. As a user, I want the selector instructed to keep the task small and select the minimum sufficient scope, so that model autonomy does not default to broad exploration.
7. As a user, I want selector failure to end the incremental run safely, so that it never falls back to expensive full-corpus exploration.
8. As a user, I want new durable knowledge to be learned even when no existing Memory is related, so that first-time lessons still persist.
9. As a user, I want the Memory planner to return only changes, so that it does not spend output tokens restating unchanged inventory, clusters, grounding, and reports.
10. As a user, I want unchanged state and receipts derived mechanically by the parent, so that deterministic work does not consume model tokens.
11. As a user, I want one small plan-repair attempt after invalid planner output, so that format mistakes do not replay the snapshot and Memory bodies.
12. As a user, I want Harness and AGENTS.md learning to reuse the same task dossier, so that they do not independently re-read the complete session or repository.
13. As a user, I want each later phase to run at most one delta planning pass, so that one task does not trigger repeated broad discovery.
14. As a user, I want no-op tasks to complete without a model call, so that no durable value means zero learning cost.
15. As a user, I want the model to decide relevance and necessary phases within prompts that explicitly require minimal exploration and delta-only work.
16. As a user, I do not want a parent-enforced token or call hard cap, so that complex but genuinely relevant tasks can still complete.
17. As a user, I want receipts to separate input, output, cache read, and cache write, so that provider totals do not obscure fresh work.
18. As a user, I want missing price data displayed as unavailable rather than zero cost, so that the UI does not imply a provider call was free.
19. As a user, I want the current parent-owned validation, privacy, rollback, path-containment, and recovery guarantees preserved, so that lower cost does not weaken safety.
20. As a user, I want full mode to remain visibly expensive and explicit, so that it cannot be triggered by automatic learning or ordinary `/consolidate`.

## Scenarios

```gherkin
Feature: Incremental continual-learning consolidation

  Scenario: Automatic learning snapshots only the completed task
    Given a long session contains many earlier tasks
    And one new user task settles
    When automatic learning freezes its evidence
    Then the dossier contains only that task, its tool activity, extension repairs, and final result
    And earlier tasks are not sent to a selector or planner

  Scenario: Default manual consolidation is incremental
    Given the project has a large Memory corpus
    When the user invokes /consolidate
    Then the pipeline uses the current task context slice
    And it does not select the complete Memory corpus by default

  Scenario: Full maintenance is explicit
    Given the project has existing Memory
    When the user invokes /consolidate full
    Then the pipeline uses the full bounded Memory corpus
    And automatic learning never selects full mode

  Scenario: A lightweight selector chooses related Memory from metadata
    Given current-task evidence and a Memory index with descriptions
    When incremental consolidation starts
    Then one lightweight selection pass receives only the task dossier and bounded Memory metadata
    And it returns the related existing Memory names
    And it is instructed to select the minimum sufficient scope

  Scenario: Selection has no arbitrary candidate-count cap
    Given more than eight Memory entries are genuinely related to the task
    When the selector evaluates their metadata
    Then it may select all related entries within the existing corpus safety bounds

  Scenario: Selector failure never triggers full exploration
    Given the selector times out or returns an invalid selection
    When the parent validates the selector result
    Then the incremental pipeline ends with a failed selection receipt
    And it does not read every Memory body
    And it does not fall back to full mode

  Scenario: New Memory can be created without related existing Memory
    Given the current task contains new durable evidence
    And the selector chooses no existing Memory
    When Memory delta planning runs
    Then it receives the current task dossier and an empty existing scope
    And it may propose bounded new Memory

  Scenario: Memory planning returns deltas only
    Given related existing Memory was selected
    When the Memory planner responds
    Then its plan contains only operations and new Memory proposals plus identity fields
    And it does not restate unchanged inventory, clusters, staleness, grounding, or reports
    And the parent derives deterministic validation and receipt state

  Scenario: No durable delta means zero planner calls
    Given the task screen finds no durable Memory, Harness, or AGENTS.md signal
    When incremental learning settles
    Then no selector or delta planner is launched
    And the receipt reports zero calls and zero tokens

  Scenario: Invalid plans receive one small repair
    Given a delta planner returns one parseable but invalid plan
    When parent validation rejects it before mutation
    Then one repair call receives only the plan, validation errors, and run identity
    And the repair call does not receive the full task snapshot, repository, or Memory bodies
    And a second failure ends the phase

  Scenario: Later phases consume one authoritative dossier
    Given the current task contains Harness and AGENTS.md evidence
    When later-phase planning starts
    Then Harness and AGENTS.md receive the same bounded dossier
    And neither planner reads the complete session snapshot
    And neither planner performs an independent repository-wide exploration

  Scenario: Incremental prompts require small work
    Given any selector or delta planner is started
    Then its instructions require the minimum sufficient scope
    And they prohibit broad repository discovery unless a selected claim names a specific file
    And they require delta-only output

  Scenario: Receipts separate token categories
    Given a provider reports input, output, cache-read, and cache-write usage
    When the learning summary is rendered
    Then every category is displayed separately
    And provider total remains available as a secondary figure

  Scenario: Missing price is not displayed as zero
    Given a provider returns token usage without reliable price data
    When the learning summary is rendered
    Then cost is displayed as unavailable
    And it is not displayed as $0.0000

  Scenario: Safety guarantees survive incrementalization
    Given a selector or delta planner proposes a change
    When the parent applies it
    Then existing identity, evidence, privacy, path, transaction, rollback, receipt, and recovery gates still apply
```

## Implementation Decisions

- Introduce a canonical **Task Slice** domain object representing exactly one settled user task, its related tool results, extension continuations, and final assistant result.
- Incremental mode is the default for automatic learning and `/consolidate`; full mode is available only through `/consolidate full`.
- A lightweight semantic selector receives the Task Slice plus Memory filename, classification, type, and description metadata. It does not receive Memory bodies or unrestricted repository discovery.
- Selector output is an exact set of existing Memory names. It has no arbitrary count cap, but remains bounded by the existing maximum corpus/file limits.
- Selector prompts require the smallest sufficient related scope. Selection failure is terminal for incremental Memory learning and never falls back to full mode.
- The selected Memory bodies and Task Slice form an authoritative **Learning Dossier**. Harness and AGENTS.md reuse this dossier.
- The model-backed explorer pass is removed. Deterministic parent code constructs the Learning Dossier from the validated selector result, task evidence, touched paths, registered skills, and Harness events.
- Incremental Memory plans contain identity fields, operations, and new Memory proposals only. Full mode may retain the exhaustive maintenance plan where full-corpus classification and grounding are explicitly requested.
- Parent code derives unchanged inventory, hashes, classifications, mirror state, receipts, and no-op results.
- A failed parseable delta plan may receive one repair call containing only the rejected plan, bounded validation errors, and identity fields. Missing/model/timeout/output-limit/stale/post-mutation failures are not repaired.
- Harness and AGENTS.md receive at most one delta planning pass each per Task Slice and may autonomously decide that no operation is warranted.
- No parent-enforced token/call hard cap is introduced. Model prompts explicitly require a small task, minimum exploration, and delta-only output.
- Receipts and summaries display input, output, cache read, cache write, provider total, and cost availability separately. Missing or unreliable price data is represented as unavailable.
- Existing safety and ownership semantics remain unchanged: children plan read-only; the parent validates, mutates, rolls back, writes receipts, and performs recovery.

## Testing Decisions

- The highest test seam is one completed user task entering the registered automatic-learning hook or `/consolidate` command and producing worker invocations, mutations, and a learning receipt.
- End-to-end harnesses will assert the exact context and Memory bodies supplied to each child rather than source-code strings.
- Selector tests cover semantic selection, empty selection, all-related selection without an arbitrary count cap, invalid names, timeouts, and fail-closed behavior.
- Task Slice tests cover long histories, extension repairs, retries, tool calls/results, compaction, and queued later tasks.
- Delta planner tests assert that exhaustive unchanged sections are neither required nor emitted in incremental mode.
- Repair tests assert that the repair request contains no snapshot path, repository exploration instructions, or Memory bodies.
- Full-mode tests assert that only `/consolidate full` selects the complete corpus.
- Receipt tests use independent literal totals and verify unavailable prices are not rendered as zero.
- Existing security, privacy, transaction, recovery, typecheck, packaging, and live-smoke tests remain mandatory.

## Out of Scope

- Model-weight training.
- Automatic promotion of incremental mode into full maintenance.
- A fixed numeric cap on semantically related Memory selection.
- Parent-enforced token or model-call budgets.
- Weakening any existing evidence, privacy, deletion, path-containment, rollback, or receipt validation.
- Treating provider cache-read tokens as equal to fresh billable input.

## Further Notes

The observed provider `totalTokens` includes cache reads and must not be presented as fresh work. In the measured failed manual run, 2,325,504 of 2,498,575 reported tokens were cache reads, while fresh input plus output was 173,071. The provider reported zero cost despite substantial usage, so cost availability must be explicit.
