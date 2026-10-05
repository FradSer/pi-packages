Feature: Temporary fork context stays in the child process's memory
  A fork inherits conversation evidence, not the parent's credentials or runtime
  authority. Temporary and durable storage are separate policies.

  Scenario: Temporary startup uses a serialized snapshot on the control pipe
    Given a detached snapshot of the parent's active context
    When a resident child starts with session policy none and that snapshot
    Then the child starts with --no-session and the explicit fork extension
    And no parent history is written to a session, temporary file or RAM filesystem
    And the control pipe carries setup before any assignment or readiness receipt
    And a correlated successful setup acknowledgement is required
    And the assignment is sent once as its own ordinary RPC prompt

  Scenario: Real native Pi consumes structured fork history on successive sends
    Given an isolated Pi 1.0.0 RPC child with a loopback-only model and no tools
    And fork history containing user, assistant, completed tool, custom and summary roles
    When the child acknowledges in-memory setup and accepts its first assignment
    Then the model request includes the fork marker in structured native history
    And summary roles use Pi's native summary conversion
    And the assignment and seed each occur once
    When a second input is accepted in that same child
    Then the seed, first input and first answer each occur once before the second input
    And setup itself is never a user message or a session entry
    And no history file exists while the child is alive or after explicit closure

  Scenario: Parent runtime authority is absent from the snapshot and wire payload
    Given system prompts, tool declarations, credentials in runtime metadata and custom state entries
    And a completed tool exchange with legacy activation metadata
    And an unfinished sibling tool call and orphan result
    When the active branch is snapshotted and serialized
    Then user and assistant content, images, provider signatures and summary roles are preserved
    And only matched completed tool exchanges are retained
    And system prompts, tool grants, deferred handles and runtime metadata are absent
    And the parent's branch and contents remain unchanged

  Scenario: Invalid or late setup does not replace existing conversation context
    Given a temporary child with initialized fork context or accepted input
    When setup is repeated, malformed, over the transport limit or sent during execution
    Then setup is rejected with a bounded correlated outcome
    And the previous seed and native child history remain unchanged
    And a generic RPC disposition handled is not evidence of successful setup

  Scenario: Fork context cannot be installed into a durable child
    Given a child with a persisted session file
    When the temporary fork setup command is received
    Then it refuses setup without changing that session

  Scenario: Session replacement releases temporary fork state
    Given a temporary child with initialized fork context
    When its session is replaced or shut down
    Then the old extension releases its in-memory snapshot
    And later model requests cannot recover that temporary history

  Scenario: Durable forks still materialize private Pi history
    Given authorized durable storage and a rebuilt context snapshot
    When writeWorkContext materializes that snapshot in the supplied private directory
    Then the private session file retains the native history and summary roles
    And its permissions remain 0600
    And it does not carry the parent's session header or runtime authority
