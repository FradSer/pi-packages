Feature: Harness audit safety boundaries
  Scenario: Native path aliases cannot bypass harness write gates
    Given isolated user and project harness paths
    When tools use tilde, at-prefixed, or file URL paths
    Then writes and edits enforce the same prohibition and schema gates
    And reads remain available for diagnosis without mutation
    And destination diagnostics lead with the supported global harness.json and project configuration choices

  Scenario: Consolidation preserves malformed predecessor data
    Given a harness file with a nonobject root, malformed rules, or retired legacy containers
    When harness consolidation or AGENTS.md skill extraction proposes a change
    Then application rejects with a structural diagnostic
    And all predecessor bytes remain unchanged

  Scenario: Planner summary uses the session skill registry
    Given valid registered and unknown flat skill rules
    When the harness planner receives its surface summary
    Then only registered rules are active
    And unknown skills appear in diagnostics
