Feature: Explicit recovery inspection
  Scenario: Read unfinished task details
    Given a blocked task with saved handoff and recovery evidence
    When the model calls get_task
    Then the full task details remain available through native expansion
    And Tasks adds no automatic waiting message
