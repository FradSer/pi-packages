Feature: Read-only original citation completeness research
  Scenario: Add existing original evidence without changing knowledge
    Given a normalized Memory and original user and tool-result entries
    When a research repair completes its citation list within existing limits
    Then retain its exact body name kind classification and original quotes
    And add only complete existing user or tool-result quotes
    And the original Jev judge decides every original support and counter check
    And no Memory Harness or production file is written

  Scenario: Unavailable citation capacity preserves the original proposal
    Given incomplete oversized sensitive or classification-changing citation input
    When research cannot add complete original quotes safely
    Then reject the input before external inference
    And never truncate invent evidence remove original quotes or infer authority
