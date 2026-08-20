Feature: Plan worker diagnostics and CLI compatibility
  As a user running /plan
  I want worker failures to explain what happened
  So that unsupported Pi options and empty worker results are actionable

  Scenario: Explore workers avoid unsupported CLI options
    Given a plan worker launches an explore child with a working directory
    When the child Pi command is constructed
    Then it does not include the unsupported --cwd option
    And explore workers include --no-extensions

  Scenario: Failed explore workers expose status and diagnostics
    Given an explore child exits without findings and reports an error
    When the plan worker records the child result
    Then the explore result status is failed
    And its diagnostics include the child error
    And the aggregate failure identifies the affected focus

  Scenario: Empty successful output is not reported as completed
    Given an explore child exits successfully without structured findings
    When the plan worker records the child result
    Then the explore result status is failed
    And its diagnostics say that no structured result was produced

  Scenario: Plan writer receives structured explore status
    Given one or more explore results have status and diagnostics
    When the plan writer prompt is assembled
    Then each result includes its status and diagnostics
