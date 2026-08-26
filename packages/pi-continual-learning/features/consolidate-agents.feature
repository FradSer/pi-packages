Feature: AGENTS.md consolidation as the third pipeline phase
  One /consolidate invocation runs a parent-owned pipeline: the memory phase,
  then the harness phase, then an AGENTS.md phase, each planning from its own
  immutable capture of the same session context (the per-phase capture is the
  established pipeline contract). The planner proposes bounded,
  evidence-cited edits to the repository-root AGENTS.md; the parent verifies
  every cited quote in code against that phase's snapshot text, simulates
  the resulting document, enforces a byte budget with zero-sum growth at
  budget, and writes only the operations the user accepts one by one.
  User-level instruction files are never touched; project state is only ever
  written through accepted operations.

  Scenario: The third phase binds to its own captured session snapshot
    Given the memory phase reported a verified consolidation and the harness phase finished
    When the AGENTS.md planning phase starts
    Then it captures a fresh immutable snapshot of the same session context
    And its plan is bound to that run's runId, scopeDigest, and snapshotDigest identity fields
    And the planner child is read-only with no extensions and read-only tools

  Scenario: Every surviving operation cites a verbatim snapshot quote
    Given a plan whose operations cite evidence quotes
    When the parent verifies the plan
    Then each quoted snippet is matched verbatim against the snapshot text in code
    And an operation whose quotes all fail verification is dropped before review
    And an operation left without any verified quote never reaches the document

  Scenario: New units require batched evidence
    Given an addUnit operation whose verified evidence occurrences total fewer than two
    When the parent validates the plan
    Then the operation is rejected unless it cites a prior-gap fingerprint recorded in the rejection ledger

  Scenario: Edits stay small steps
    Given a plan declaring more than five operations
    When the parent validates the plan
    Then the whole plan is rejected and the document is not modified

  Scenario: The byte budget gates document growth
    Given a current AGENTS.md smaller than the configured budget
    When the simulated post-edit document exceeds the budget
    Then the plan is rejected before review
    When the current document is already at or above the budget
    Then only plans whose post-edit document is no larger than the current document are accepted

  Scenario: Narrow instructions are extracted instead of deleted
    Given an extractUnit operation targeting memory or a skill prompt
    When the parent applies the accepted plan
    Then the extracted unit is removed from AGENTS.md
    And a memory extraction creates a canonical memory file owned by the memory roots
    And a skill-prompt extraction merges into the project-local harness layer

  Scenario: Per-operation human review gates the write
    Given a schema-valid, quote-verified, in-budget plan with operations
    When the session has a TUI
    Then each operation is presented individually and the user accepts or rejects it
    And only accepted operations are applied in one atomic write
    And extraction artifacts are written before the document so a failed write never orphans an extracted unit
    And a post-apply receipt records digests, accepted operations, and rejected fingerprints
    When the session has no TUI
    Then no project state is written and the phase reports that review is required

  Scenario: Rejected operations are remembered
    Given the user rejected one or more reviewed operations
    When a later consolidation run proposes an operation with the same fingerprint
    Then the repeated proposal is dropped unless it cites new evidence quotes
    And the ledger is capped so it cannot grow without bound

  Scenario: User-level instruction files are never touched
    Given the consolidated project resolves its instruction target
    When the phase selects the file to edit
    Then the target is exactly <cwd>/AGENTS.md and never a user-level AGENTS.md
    And a missing project AGENTS.md is a verified skip, not an error

  Scenario: Ambiguous anchors fail closed
    Given an operation whose oldText or anchor matches the document more than once or not at all
    When the parent simulates the plan
    Then the simulation fails and no write occurs

  Scenario: The AGENTS.md phase failure isolates from earlier results
    Given memory results were already applied and verified
    When the AGENTS.md phase fails to plan, verify, or apply
    Then memory and harness results remain untouched
    And the user receives an AGENTS.md-specific diagnostic instead of an overall failure

  Scenario: no-context skips the AGENTS.md phase
    Given the user invoked /consolidate no-context
    When the pipeline reaches the third phase
    Then no planner child is spawned and the user is informed why
