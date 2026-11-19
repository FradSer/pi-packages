Feature: Current task information survives tool reads and refused transitions
  Scenario: A new blocker follows an earlier recovery
    Given a task has an earlier recovery explanation
    And a new operational blocker prevents work
    When the caller reads the task
    Then the model text identifies the current blocker
    And the earlier recovery explanation remains historical

  Scenario: A mixed update omits the completion outcome
    Given a caller updates the task description and requests completion
    When the caller supplies no completion outcome
    Then completion is refused
    And the response identifies the retained description update
    And the task remains in its previous state
