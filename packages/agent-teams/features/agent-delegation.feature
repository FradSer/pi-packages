Feature: Strict Agent actions
  Agent lifecycle is explicit and incarnation-bound.

  Scenario: Prompted start acknowledges independent execution
    When the Leader calls agent start with a prompt for a disk-defined or inline Agent
    Then native input acceptance is acknowledged before its receipt
    And the receipt contains an incarnation-bound session handle
    And a settled result leaves that same incarnation idle for send

  Scenario: Prompt-less start creates an unassigned resident
    When the Leader calls agent start without a prompt
    Then one resident starts without Work ownership

  Scenario: Inspect and stop require exact session identity
    Given an Agent has a current session handle
    When the Leader calls agent inspect or stop with that handle
    Then only the matching incarnation is observed or stopped
