Feature: Bound observational Jev same-batch Memory relationships
  Scenario: Original complete candidate review permits relation observation
    Given normalized new Memory candidates and a complete frozen support review
    When the parent requests all original unordered relationships
    Then the existing Jev client evaluates the unchanged structured pair question
    And every observation binds original evidence, candidates, existing bodies and actual model
    And no relationship observation grants write permission

  Scenario: Whole original input fails eligibility or any request preflight
    Given private data without permission, sensitive later evidence, bad citation or over-capacity inputs
    When relationships are requested
    Then no external request is made
    And the parent retains the original proposal

  Scenario: Transport fails or original identity changes
    Given unavailable, timeout, cancellation, invalid output or a mismatched actual model
    Or original input mutated during an asynchronous request
    When relationships are requested
    Then no complete relationship proof is returned
    And known usage remains a lower bound rather than a free complete run

  Scenario: Relationship is dependent, conflicting, duplicate or uncertain
    Given valid structured answers at unchanged thresholds
    When relationship observations return
    Then they retain their actual relation and uncertainty
    And they never become an allow decision or a file operation
