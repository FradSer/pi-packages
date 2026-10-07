Feature: Research composed readiness without changing write authority
  Scenario: A self-contained supported record survives an unsupported conflicting proposal
    Given complete frozen support and pair reviews of every original candidate
    And one candidate is held by original support verification
    When a strict bound standalone review confirms the supported candidate is complete
    Then only that supported candidate is research-recoverable
    And no write plan or permission is returned

  Scenario: Applied candidates still require compatible independent pairs
    Given two support-passed candidates with strict standalone observations
    When their original pair is conflicting, dependent, duplicate or uncertain
    Then both tentative candidates remain held

  Scenario: Original successful observations survive an unavailable standalone review
    Given the original complete review already establishes a recoverable candidate
    When the additional standalone proof is unavailable, invalid or stale
    Then the research falls back to the original recoverable indexes
    And it cannot recover any additional candidate

  Scenario: Complete original checks remain mandatory
    Given missing citations, altered privacy, missing evidence windows or stale bindings
    When composed readiness is simulated
    Then no additional candidate is recoverable
    And operations and writes remain forbidden
