Feature: Preserve parent-owned bindings in the single semantic Harness repair
  Scenario: A semantic correction keeps rule identity and original evidence
    Given a parent-validated Harness plan held by Jev
    When its existing read-only repair slot is used
    Then the worker receives exact retained operation identity and original evidence bindings
    And only the evidence operation index may change when omissions reindex the plan
    And all final parent and Jev checks still run before writes
  Scenario: A repair changes protected fields
    Given a repair with a foreign rule identity or changed original citation
    When the parent validates retention
    Then it preserves the original proposal without applying the repair
    And the receipt reports a controlled identity or citation mismatch category
    And no second repair or extra model call is started
