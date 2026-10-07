Feature: Real project verification has observed execution provenance
  Scenario: A command is requested before its success is known
    Given a frozen project regression task
    When its initial prompt is prepared
    Then the command is requested as a standalone invocation
    And its success is not declared before execution
    And learning must preserve uncertainty if success is unavailable

  Scenario: A successful tail process cannot verify a test process
    Given a test command piped into tail and a non-error tool result
    When the learning-phase execution is checked
    Then it does not satisfy standalone verification
    And a later independent project check does not rewrite frozen learning evidence
