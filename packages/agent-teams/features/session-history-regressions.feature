Feature: Attempt-safe recovery after failures and supersession
  Scenario: Failed work waits for deliberate recovery
    Given a worker owns a work item and its dependent is pending
    When the worker submits failure and execution settles
    Then one failure result is delivered
    And the work item is retained but not autonomously claimable
    And only explicit leader recovery can authorize another attempt
    And the dependent remains blocked

  Scenario: Superseded holder can finish cancellation
    Given an assignment is closed by supersession but still retains its work and resources
    When worker tools are refreshed for the cancellation notice
    Then the work tool remains exposed for submitting failure or release
    And no new work can be claimed before cancellation settles
    And after submission further communications cannot create a cancellation loop

  Scenario: An old turn cannot borrow a new assignment identity
    Given a worker turn started for assignment A
    And the authoritative roster now contains assignment B
    When the old turn sends an agent event or submits work
    Then it cannot emit a message or submission with assignment B authority
    And assignment B is not affected by the old turn
