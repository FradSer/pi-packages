Feature: Prompt-budget measurements use controlled inputs

  Scenario: Ambient saved Agents do not alter the fixed guidance budget
    Given personal Agent definitions exist outside the benchmark
    When the benchmark measures the fixed guidance sections
    Then it uses an empty isolated Agent catalog and project directory
    And it does not read personal credentials or definitions
    And existing section and total ceilings stay unchanged
