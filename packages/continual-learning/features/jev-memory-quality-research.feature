Feature: Evaluate Memory usefulness and requested completeness separately
  Scenario: A supported transient observation has no lasting use
    Given a candidate accurately repeats a task-only temporary failure
    When its independent usefulness judgment is negative
    Then the experimental combination retains a proposal instead of allowing it

  Scenario: An explicitly requested historical result remains eligible
    Given the user explicitly asks to remember a verified historical result
    When usefulness is positive and no requested information is missing
    Then the experimental quality check permits further parent validation
    And this does not grant permission to write Memory or change Harness

  Scenario: Source-supported text omits a requested condition
    Given all candidate claims are supported but a required condition is absent
    When completeness is evaluated against the whole resulting Memory
    Then the experiment retains the proposal with a controlled missing-knowledge reason

  Scenario: Knowledge is already present in another Memory
    Given the requested information is preserved across the resulting Memory bodies
    When completeness is judged
    Then it does not demand every individual candidate repeat all requested knowledge

  Scenario: A quality judgment is uncertain or unavailable
    Given an uncertain, missing or malformed typed answer
    When experimental quality answers are combined
    Then they cannot allow a write or erase the Memory opportunity
    And the research does not change the production defaults or commands
