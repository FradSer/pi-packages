Feature: Strict Agent actions
  Agent lifecycle is explicit and incarnation-bound.

  Scenario: Delegate creates independent Work
    When the Leader calls agent delegate for a defined or inline Agent
    Then a Work Item, Assignment Attempt, and Work Session start
    And the receipt contains an incarnation-bound session handle

  Scenario: Start creates an unassigned resident
    When the Leader calls agent start
    Then one resident starts without Work ownership

  Scenario: Inspect and stop require exact session identity
    Given an Agent has a current session handle
    When the Leader calls agent inspect or stop with that handle
    Then only the matching incarnation is observed or stopped
