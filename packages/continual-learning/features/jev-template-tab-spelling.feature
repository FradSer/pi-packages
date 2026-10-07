Feature: Recognize equivalent tab spelling without inferring user authority
  Scenario: A generator writes literal tabs in the exact bounded template
    Given a new blocking rule with matching frozen parent identity
    And its pattern differs from the project template only by literal tabs replacing escaped tabs
    When semantic validation prepares its questions
    Then code supplies the existing bounded matching proof
    And Jev still checks user authority, argument scope, explanation and every counter window
    And the original rule is not rewritten

  Scenario: Equivalent syntax cannot bypass limits
    Given a rule with changed scope, unknown syntax, approval action or stale parent identity
    When its pattern contains literal tabs
    Then no new matching proof is supplied
    And conditional authority, counterevidence and unavailable judgments remain proposals
