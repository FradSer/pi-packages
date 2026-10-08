Feature: Execution records do not become task reminders

  Scenario: A direct execution fails
    Given an internal execution record and an explicit user task
    When execution fails and the model settles
    Then the failed execution evidence remains readable
    And only the user task participates in continuation

  Scenario: Earlier generated execution records are restored
    Given a saved generated work record from an earlier runtime
    When task state is restored
    Then the record is classified as execution history
    And it remains in `blocked` without triggering task continuation

  Scenario: Invalid present classification stays visible for recovery
    Given saved task metadata has an invalid recordKind value
    When task state is restored
    Then its classification is repaired to task in a reported `blocked`
    And evidence stays readable
    And generated-id inference does not hide the invalid record

  Scenario: An explicit task retains continuation
    Given an ordinary task under a blocked state
    When the model settles
    Then the task receives blocker inspection
    And its hold is not cleared automatically
