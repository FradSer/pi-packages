Feature: Independently observe real project learning phases
  Scenario: Held Harness does not hide successful Memory use
    Given a real-project workflow has applied valid public and private Memory
    And the Harness candidate remains a proposal
    When independent learning effects are evaluated
    Then the Memory phase passes and its fresh-session recall is observed
    And the Harness phase fails its original application gate
    And overall acceptance remains failed

  Scenario: Missing Harness judgment does not invalidate Memory participation
    Given Memory has a supported pinned real Jev judgment
    And no supported Harness judgment is available
    When independent phase participation is evaluated
    Then Memory participation can pass on its own evidence
    And the missing Harness judgment remains a Harness failure

  Scenario: Other stage failures remain overall failures
    Given Memory and Harness observations pass
    And a selector failed or an agents stage was cancelled
    When overall acceptance is evaluated after independent observations
    Then the successful observations remain recorded
    And overall acceptance remains failed
