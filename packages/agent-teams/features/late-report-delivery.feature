Feature: Assignment completion and delayed report delivery have explicit meanings
  Scenario: Pi delivers an accepted report after its process has stopped
    Given a worker report has already been handed to Pi during a leader tool call
    When the worker is shut down before that tool call finishes
    Then Pi still delivers the original report at the next safe boundary
    And the report is marked as delivered after the process stopped
    And collapsed and expanded report rows both show the late-delivery label
    And the authored time, delivery time, stop time, and original body are preserved
    And delivery does not make the worker live again

  Scenario: A terminal report finishes an assignment, not a resident process
    Given a terminal report from a resident worker
    When the finish entry is rendered
    Then it describes the assignment as finished
    And it does not describe the agent process as stopped

  Scenario: Normal reports are not marked as late
    Given a report whose process has not stopped
    When Pi delivers the report
    Then no after-stop marker is added
    And stopping the process after delivery starts does not retroactively mark the report as late
