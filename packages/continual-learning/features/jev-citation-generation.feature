Feature: Evidence-complete Memory generation and bounded semantic repair
  Scenario: Current-state and verified-result facts require relevant original citations
    Given a frozen dossier contains future instructions and actual verification
    When a Memory candidate is generated or semantically repaired
    Then guidance distinguishes intended future use from verified current state
    And every body and description claim cites its relevant original source
    And later corrections and exceptions are preserved without citing unrelated entries

  Scenario: Existing parent authority remains decisive
    Given missing, sensitive, oversized or contradictory evidence
    When the one existing read-only repair is requested
    Then guidance forbids invented evidence and unverified success claims
    And exact quote validation, privacy, retained candidate identity and full Jev checks still decide application
    And unavailable Jev does not consume a new repair or release Harness constraints

  Scenario: The repair schema demonstrates a grounded index description
    Given a rejected Memory needs a read-only repair
    When the repair worker receives its schema example
    Then the example description repeats a concrete fact from its example body
    And the example cannot serve as evidence for a real candidate
