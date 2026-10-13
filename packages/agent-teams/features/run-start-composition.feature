Feature: Structured run-start guidance
  Scenario: Leader guidance composes with another extension
    Given another extension contributes a prompt section and a guideline
    When an idle or active leader starts a run
    Then leader guidance uses an owned named section without a full prompt override
    And the other extension's contributions remain unchanged

  Scenario: A worker starts from a custom message
    Given a worker has no current assignment
    When a custom message starts a run without a prompt
    Then worker guidance uses an owned named section
    And task disclosure does not fail or infer a task notice

  Scenario Outline: Pi renders guidance with either preamble
    Given Pi 1.2 uses a <mode> system prompt
    When a leader or worker contributes its guidance
    Then the rendered sections contain the guidance and the unchanged preamble
    Examples:
      | mode    |
      | default |
      | custom  |
