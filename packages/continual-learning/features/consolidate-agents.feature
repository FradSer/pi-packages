Feature: AGENTS.md consolidation as the third pipeline phase
  One /consolidate invocation runs a parent-owned pipeline: the memory phase,
  then Harness and AGENTS.md planning against one later-phase immutable capture
  of the same frozen session context. The planner proposes bounded,
  evidence-cited edits to the repository-root AGENTS.md; the parent verifies
  every cited quote in code against that phase's snapshot text, simulates
  the resulting document, enforces a byte budget with zero-sum growth at
  budget, and autonomously applies only operations that pass every gate.
  User-level instruction files are never touched; project state is only ever
  written through validated operations.

  Scenario: The third phase binds to the shared task dossier and snapshot
    Given the selector wrote the authoritative Learning Dossier
    And Harness and AGENTS.md planning may overlap
    When the AGENTS.md planning phase starts
    Then it receives the same dossier path and immutable task-slice snapshot as Harness planning
    And it performs no independent model exploration or repository-wide discovery
    And its plan is bound to that run's runId, scopeDigest, and snapshotDigest identity fields
    And the planner instructions come from the package-owned agents/agents-md-consolidator.md resource
    And the child disables extension, skill, prompt-template, context-file, and theme discovery

  Scenario: Every surviving operation cites an indexed user or tool-result quote
    Given a plan whose operations cite evidence quotes and immutable snapshot entry indexes
    When the parent verifies the plan
    Then each quoted snippet is matched verbatim inside the cited user or tool-result content leaf
    And assistant text, snapshot metadata, uncited entries, and unindexed quotes never count as evidence
    And an operation whose quotes all fail verification is dropped before automatic application
    And an operation left without any verified quote never reaches the document

  Scenario: New units require parent-counted batched evidence
    Given an addUnit operation whose quote repeats inside one snapshot entry or claims a planner occurrence count
    When the parent validates the plan
    Then the parent counts distinct matching user or tool-result snapshot entries itself
    And the operation is dropped unless its verified evidence spans at least two distinct entries

  Scenario: Edits stay small steps
    Given a plan declaring more than five operations
    When the parent validates the plan
    Then the whole plan is rejected and the document is not modified

  Scenario: The byte budget gates document growth
    Given a current AGENTS.md smaller than the configured budget
    When the simulated post-edit document exceeds the budget
    Then the plan is rejected before automatic application
    When the current document is already at or above the budget
    Then only plans whose post-edit document is no larger than the current document are automatically applied

  Scenario: Narrow instructions are transactionally extracted instead of deleted
    Given an extractUnit operation targeting memory or a skill prompt
    When the parent autonomously applies the validated plan
    Then the extracted unit is removed from AGENTS.md in the same rollback boundary as its artifact and receipt
    And every memory extraction declares safe or private independently of its memory type
    And a safe memory extraction is byte-identical in the private root and project mirror
    And a private memory extraction exists only in the private root and is marked harness only
    And pre-existing private index classifications remain unchanged
    And an existing memory name is never overwritten, including case-insensitive matches
    And duplicate case-insensitive memory extraction names within the same plan are rejected before mutation
    And a skill-prompt extraction merges into the project-local harness layer without overwriting existing guidance
    And a symlinked project .pi path cannot redirect skill guidance outside the project
    And swapping either captured Memory root to a symlink during apply fails before redirected writes

  Scenario: Extraction failure or cancellation rolls back every surface
    Given a validated plan that extracts memory or skill guidance
    When artifact creation, cancellation, the AGENTS.md write, or receipt persistence fails
    Then the memory roots, indexes, project-local harness layer, AGENTS.md, and receipt are restored to their exact pre-apply state
    And Memory roots and the project .pi directory that were absent before apply are absent again when rollback leaves them empty
    And the successful post receipt retains the secure pre-apply recovery receipt, while normal failure or cancellation deletes it
    And the application result reports failed or cancelled with zero applied operations

  Scenario: A later session recovers an interrupted extraction transaction
    Given an AGENTS.md pre-apply receipt exists without its matching post receipt
    And the previous process stopped after partially mutating an allowed Memory, Harness, or instruction target
    When the package starts another session for the same canonical project
    Then the parent validates the recovery receipt against that project's exact allowed paths
    And it restores predecessor files and directory absence before new learning starts
    And it removes the consumed pre-apply receipt so recovery is idempotent
    But a malformed, symlinked, foreign-project, or path-escaping receipt fails closed

  Scenario: Validated AGENTS.md changes apply autonomously
    Given a schema-valid, quote-verified, in-budget plan with operations
    When the planner phase completes
    Then every surviving operation is applied without a TUI prompt
    And a pre-apply recovery receipt records exact predecessor state before mutation
    And a post-apply receipt records digests and applied operation fingerprints
    And the structured planning and application outcomes distinguish applied, no-op, rejected, failed, skipped, and cancelled attempts
    And safety validation remains the only gate before the atomic transaction

  Scenario: Planner termination is awaited before returning
    Given the AGENTS.md planner child was spawned
    When planning times out, exceeds its output bound, or is cancelled after spawn
    Then the parent awaits bounded child termination before returning or releasing the run

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
