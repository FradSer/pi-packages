Feature: Harness consolidation alongside memory consolidation
  One /consolidate invocation runs a parent-owned pipeline: the established
  read-only memory planning phase, followed by a harness phase that mines the
  same immutable session snapshot for tool-call guardrail evidence (blocked
  calls, confirm outcomes, user corrections) and applies bounded changes only
  to the personal project-local harness layer. The harness phase never mutates
  memory results and never writes shared config layers.

  Scenario: /consolidate consolidates both surfaces
    Given manual consolidation completes successfully with context captured
    When the memory phase reports a verified consolidation
    Then a harness planning phase starts against the same session history
    And its plan is validated against the same run identity fields

  Scenario: The harness planner mines guardrail evidence from history
    Given the captured session contains blocked tool calls, confirmation outcomes, or user corrections
    When the harness planner reads the immutable snapshot
    Then every proposed operation cites concrete observed evidence from that snapshot
    And the parent alone writes any configuration

  Scenario: Harness operations are bounded
    Given a harness plan declares more than the configured maximum operations
    Or a single policy payload exceeds the configured byte bound
    When the parent validates the plan
    Then the plan is rejected and no harness file is modified

  Scenario: Harness plans bind to the run identity
    Given a harness plan whose runId, scopeDigest, or artifactHash disagrees with the run
    When the parent extracts the plan
    Then the plan is rejected before any validation of its operations

  Scenario: Application targets only the project-local layer atomically
    Given a schema-valid harness plan
    When the parent applies it
    Then changes merge into <project>/.pi/harness.local.json in one atomic write
    And shared layers user, user.local, and project are never written
    And a pre-apply receipt records the prior file digest and a post-apply receipt records the final digest

  Scenario: Harness phase failure isolates from memory results
    Given the memory phase already applied and verified its results
    When the harness phase fails to produce a valid plan or fails to apply
    Then memory results remain untouched
    And the user receives a harness-specific diagnostic instead of an overall failure

  Scenario: no-context skips the harness phase
    Given the user invoked /consolidate no-context
    When the memory phase finishes
    Then no harness planner child is spawned
    And the user is informed that harness consolidation needs captured context

  Scenario: Concurrent invocations stay single-flight across both phases
    Given a consolidation pipeline is running in either phase
    When another /consolidate is triggered
    Then no second planner child is started
