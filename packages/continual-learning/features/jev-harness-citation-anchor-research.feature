Feature: Read-only research on citation anchoring for Harness argument scope
  Scenario: Show the exact original user restriction in the existing scope question
    Given a parent-valid command-family rule with a matching original user citation
    When preparing the research after arm
    Then the existing family question also contains the original citation
    And its criteria, matching proof, complete frozen state and counter questions are unchanged
    And the research cannot write or authorize the rule
  Scenario: A quotation is not present in user evidence
    Given an invented quote or an assistant-only matching quote
    When preparing the research request
    Then preparation rejects before any external request
  Scenario: A later permission exception remains visible
    Given a general restriction followed by an exception in the same entry or later evidence
    When preparing the research request
    Then the full original state and counter review remain intact
    And quotation visibility is never itself permission
