Feature: Communication-only Agent Event
  Agent Event carries only communication intent.

  Scenario: Participants exchange an informational event
    Given a leader and exact Work Sessions
    When a participant calls agent_event with message, recipient, and inform or request intent
    Then the runtime binds sender identity and routes the event to the exact recipient
    And the event does not complete, release, reopen, assign, or supersede Work
