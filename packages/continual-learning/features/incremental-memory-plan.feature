Feature: Expand an incremental Memory delta into the full parent-owned plan
  Incremental planners describe only proposed changes. The parent derives the
  exhaustive validation shape from the immutable consolidation run and exact
  selected Memory names before existing validation or mutation can occur.

  Scenario: Parent expands a valid delta without model-authored unchanged state
    Given a ConsolidationRun whose private MEMORY.md classifies one safe and one private selected Memory
    And a delta plan with matching identity fields, one selected rewrite, and one new Memory proposal
    When the parent expands the delta for the exact selected names
    Then the full plan contains the exact selected inventory with parent-derived classifications
    And every selected item belongs to one deterministic cluster
    And unchanged items receive KEEP staleness, UNVERIFIABLE grounding, and an unchanged report
    And the expanded plan is compatible with the existing validator and applyConsolidationPlan

  Scenario: Repository observations are accepted only after parent validation
    Given a selected project Memory delta operation cites bounded repository observations
    When every cited path is repository-relative, has an allowed status, and a found path is an existing file
    Then the full plan uses those observations for that Memory's grounding record
    But an invalid, escaping, or nonexistent found observation is rejected

  Scenario: Delta identity and scope fail closed
    Given a delta plan has a foreign run identity, an operation outside selected, or a duplicate selected or operation name
    When the parent attempts expansion
    Then expansion is rejected before producing a full plan

  Scenario: Parent classifications cannot be overridden
    Given private MEMORY.md classifies a selected Memory as private
    When the delta operation labels it safe or uses an invalid classification
    Then expansion is rejected

  Scenario: Deletes require an allowed explicit verdict and verifiable preservation
    Given a delta operation deletes selected Memory
    When it omits an allowed CONTRADICTED, SUPERSEDED, or SUBSUMED verdict
    Then expansion is rejected
    And KEEP is derived for all operations that do not explicitly authorize deletion
    And preservation targets remain subject to the existing validator
