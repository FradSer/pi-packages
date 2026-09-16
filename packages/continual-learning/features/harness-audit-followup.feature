Feature: Harness audit safety boundaries
  Scenario: Native path aliases cannot bypass harness write gates
    Given isolated user and project harness paths
    When tools use tilde, at-prefixed, or file URL paths
    Then writes and edits enforce the same prohibition and schema gates
    And reads remain available for diagnosis without mutation
    And destination diagnostics lead with the supported global harness.json and project configuration choices

  Scenario: Consolidation preserves malformed predecessor data
    Given a harness file with a nonobject root or malformed policies, disabled, or skillPrompts container
    When harness consolidation or AGENTS.md skill extraction proposes a change
    Then application rejects with a structural diagnostic
    And all predecessor bytes remain unchanged

  Scenario: Planner summary uses the session skill registry
    Given valid registered and unknown skill prompts
    When the harness planner receives its surface summary
    Then only registered prompts are active
    And unknown prompts appear in diagnostics
