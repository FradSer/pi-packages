Feature: Parent-controlled independent Memory subset transaction research
  Scenario: A supported subset is eligible and parent permits application
    Given a complete frozen original new-Memory plan and independent-pair proof
    When the parent prepares a partial application
    Then the complete original proposal is persisted before application
    And only original eligible indexes enter the unchanged parent writer
    And original scope, citations, text and privacy remain unchanged

  Scenario: Parent denies application or independence proof is incomplete
    Given an original proposal with an explicit memory request
    When partial application is prepared without permission or valid proof
    Then the complete original proposal remains persisted
    And no application is invoked

  Scenario: Proposal persistence fails or frozen inputs change
    Given a recoverable subset
    When preservation fails or input changes during an asynchronous step
    Then no application is invoked

  Scenario: Actual parent Memory writing is cancelled mid-transaction
    Given a persisted original proposal and a permitted independent subset
    When the existing parent writer observes cancellation after its first write
    Then both Memory roots roll back
    And the original proposal remains available
