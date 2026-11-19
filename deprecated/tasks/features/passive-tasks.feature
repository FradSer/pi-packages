Feature: Passive task records
  Scenario: Open work does not control settlement
    Given pending, held and blocked tasks
    When the model ends its response after successful tool work
    Then Tasks adds no message and requests no additional turn
    And task records remain unchanged

  Scenario: Tools provide explicit completion checks
    Given unfinished tasks with saved blockers and evidence
    When the model lists pending, in-progress and blocked tasks and reads their details
    Then the tools return the saved task state
    And Tasks does not inject instructions into model requests
