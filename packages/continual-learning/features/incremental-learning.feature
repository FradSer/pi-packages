Feature: Select the minimum sufficient scope for incremental learning
  Routine continual learning works from one completed task and bounded Memory
  metadata, then constructs one authoritative dossier without broad discovery.

  Scenario: The current task slice excludes history and a queued later task
    Given a session contains earlier completed tasks, one completed current task, and a queued later user task
    When the parent constructs the current Task Slice
    Then it contains the current user request, tool activity, extension continuations, and final assistant result
    And it excludes earlier tasks and the queued later task

  Scenario: The selector receives metadata without Memory bodies
    Given current-task evidence and a Memory index with classifications, types, and descriptions
    When incremental Memory selection starts
    Then the selector prompt contains the Task Slice and bounded Memory metadata
    And it does not contain Memory bodies, read paths, broad repository discovery instructions, or tools
    And it requires the minimum sufficient scope

  Scenario: Selection has no arbitrary candidate-count cap
    Given more than eight Memory entries are genuinely related to the task
    When the selector returns every exact related name
    Then the parent accepts every selected entry within the existing corpus safety bounds

  Scenario: New Memory can be planned from an empty existing scope
    Given the current task contains new durable evidence
    And the selector chooses no existing Memory
    When the parent builds the Learning Dossier
    Then the dossier contains the Task Slice and an empty selected Memory list
    And Memory planning remains enabled

  Scenario: Selector routing cannot suppress deterministic durable evidence
    Given the parent screen identifies durable Memory or Harness evidence in the Task Slice
    When the selector omits that phase from its routing flags
    Then the parent keeps the deterministically selected phase enabled

  Scenario: Selector failure is fail-closed
    Given the selector times out, returns ambiguous objects, or names unknown Memory
    When the parent validates the selector result
    Then incremental selection fails without writing a dossier
    And it does not fall back to reading every Memory body or full mode

  Scenario: A verbose selector response may contain one balanced object
    Given the selector wraps one valid selection object in prose or a code fence
    When the parent parses the selector response
    Then the exact selection is accepted
    But multiple balanced selection objects are rejected as ambiguous

  Scenario: The authoritative dossier contains selected evidence once
    Given the selector chooses related existing Memory
    When the parent writes the Learning Dossier
    Then the Task Slice appears once
    And each selected Memory body appears once
    And unselected Memory bodies do not appear
