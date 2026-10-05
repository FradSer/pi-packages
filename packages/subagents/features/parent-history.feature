Feature: Durable child history belongs to one parent Pi session

  Memory and ordinary scratch belong to the disk identity. Conversation history
  belongs to that identity, project and the trusted parent session identifier.
  No model-facing parameter selects or changes the parent identifier.

  Scenario: History ownership comes from the parent session
    Given a disk identity and the intent tool interface
    When parent session A starts and stops the identity
    And parent session B starts and stops the same identity in the same project
    Then their native children use different private session directories
    And both use the same Memory and scratch home and original project cwd
    When parent session A restarts the identity
    Then it resumes A's history without importing B's history

  Scenario: Native parent identity is stable when its Pi session is reopened
    Given two actual isolated parent Pi sessions with one disk identity and project
    When both start children while the other child is still alive
    Then both startups succeed with distinct parent-scoped history paths
    When each parent is stopped and reopened from its own Pi session file
    Then each child restores only that parent's previous conversation
    And both can read the shared Memory and scratch content
    And every native child closure is observed

  Scenario: Existing project-only history remains preserved
    Given private history from before parent-scoped storage
    When a parent starts the disk identity
    Then its own private history starts without importing the old conversation
    And the old history is neither moved, overwritten nor deleted

  Scenario: Headless library callers can supply a stable parent identity
    Given an embedding with no native Pi execution context
    When it supplies a trusted parentSessionId in runtime options
    Then that identifier determines its own history partition
    And omitted identifiers use a process-local identity rather than shared project history
