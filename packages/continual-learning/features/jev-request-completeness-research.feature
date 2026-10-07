Feature: Research explicit Memory requirements as separate frozen-source judgments
  Scenario: A requested placement is missing although the marker is present
    Given the original user requests that a report begin with a marker
    And the resulting Memory mentions the marker without its placement
    When the frozen placement requirement is judged independently
    Then a negative preservation answer is incomplete
    And the research result grants no write permission

  Scenario: Requested facts are distributed across resulting Memory bodies
    Given all required facts survive across old and new Memory bodies
    When each original requirement is compared to the whole resulting inventory
    Then equivalent wording and distributed storage may be complete
    And inventory mutation and source validation still precede inference

  Scenario: A requirement list is partial, invalid or uncertain
    Given invalid original quote offsets or duplicate source spans
    When research questions are prepared
    Then code rejects them before transport
    Given a missing, malformed or uncertain answer
    When preservation answers are combined
    Then it cannot become a complete result
    And complete only covers supplied requirements, not their extraction or authorization
