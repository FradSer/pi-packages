Feature: Learning state remains bound to its task and project
  Scenario: Shutdown during receipt persistence cancels subsequent effects
    Given a pipeline is writing its receipt
    When the session shuts down before that write completes
    Then it emits no learning result and queues no skipped task afterward

  Scenario: Corrupt task references remain visible in status
    Given a scoped backlog containing only a malformed record
    When the user inspects memory status or consolidation backfill
    Then both diagnostics report the malformed reference count
    And neither command starts a learning model

  Scenario: A corrupt settings file does not enable automatic learning
    Given automatic learning was disabled and its settings become invalid
    When a task settles
    Then no learning worker starts and the invalid settings are reported

  Scenario: A skipped task is recorded only for its project
    Given two projects share an agent directory
    When a task is skipped in one project
    Then its reference appears only in that project's backlog

  Scenario: Invalid model fields cannot silently select the session model
    Given memory.json explicitly contains non-string or empty provider and model fields
    When the learning model configuration is read
    Then the configuration is reported as invalid without overwriting it
    And an empty configuration object still allows the documented session-model fallback

  Scenario: Invalid learning model configuration blocks every phase
    Given memory.json specifies an invalid model configuration
    And an automatic task may select Harness even when automatic Memory is off
    When learning starts
    Then no selector or phase worker runs
    And no Memory normalization changes learned bytes
    And a private failure receipt reports the blocked start

  Scenario: The session model is frozen when no learning model is configured
    Given memory.json has no provider/model pair and a session model is selected
    When the learning model changes during selection
    Then every planner in that pipeline uses the original session model
    And the next pipeline uses the newly configured learning model

  Scenario: A missing consumed session does not move the cursor
    Given the first backlog record is consumed
    When that record's session disappears
    Then later readable records remain pending

  Scenario: Backlog storage is bounded and never follows symlinks
    Given unsafe or full backlog storage
    When a skipped task is queued
    Then existing files are preserved and the queue reports failure

  Scenario: A manual task is frozen before recovery
    Given manual learning is preparing recovery
    When another task arrives
    Then the learner uses only the original frozen task

  Scenario: Shutdown during preparation cannot restart learning
    Given learning is waiting for recovery
    When the session shuts down
    Then no selector or planner starts and all locks are released

  Scenario: Legacy consumption never hides newly scoped tasks
    Given a legacy global cursor and a new project-scoped task reference
    When the project backlog is inspected
    Then the new reference remains pending

  Scenario: Concurrent backlog mutations stay within their storage contract
    Given two processes try to append at the storage limit or update a cursor
    When one mutation owns the backlog lock
    Then another mutation cannot exceed the cap or regress the cursor

  Scenario: Repeated results retain their actual task positions
    Given two tasks contain identical assistant results
    When the later task is skipped
    Then its reference names the later task's original branch positions

  Scenario: Status explains the learning loop without starting it
    Given automatic learning is off and one task was skipped
    When memory status is requested
    Then it reports knowledge, automatic policies, pending references and pipeline state
    And no learner starts
