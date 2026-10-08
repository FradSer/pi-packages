Feature: Learning preserves authority and concurrent edits
  Scenario: Literal planner bindings remain literal
    Given a supplied path contains another placeholder token
    When the parent renders a planner prompt
    Then the supplied path remains byte-identical
  Scenario: A human edits a transaction predecessor
    Given learning has frozen its predecessors
    When a human changes a file before apply or during failed verification
    Then learning preserves the human edit and reports a conflict
  Scenario: Worker inspection stays in its frozen scope
    Given a planner has an explicit read inventory
    When it requests an outside file or a symbolic link
    Then the read is rejected before any bytes are returned
  Scenario: Distinct canonical projects collide in the legacy readable key
    Given one project owns the persisted readable scope
    When another project resolves the same scope
    Then resolution refuses cross-project access without changing existing data
  Scenario: Management exceeds the discovery index budget
    Given a project contains more than 128 memories
    When the user browses memories
    Then every supported entry is reachable through pages
  Scenario: Automatic learning has a meaningful result
    Given automatic learning applies, proposes, fails, rejects or cancels a change
    When the pipeline settles
    Then one compact receipt is visible without starting another turn
  Scenario: Frozen evidence omitted entries
    Given the task slice omitted original entries
    When learning selects an apply policy
    Then the parent downgrades learning to proposals and reports incomplete evidence
  Scenario: A transaction directory is replaced before recovery
    Given learning owns a newly created file and has recorded its predecessor
    When a directory ancestor is replaced during verification or before interrupted recovery
    Then rollback refuses the changed path and preserves files outside the transaction
