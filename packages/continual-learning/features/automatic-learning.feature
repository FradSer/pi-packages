Feature: Learn from settled user tasks without a memory command
  Automatic learning is controlled by the persisted auto-memory setting.
  Children propose bounded changes and only the parent validates and applies them.

  Scenario: A settled user task starts learning exactly once
    Given auto-memory is enabled and a real user has submitted a task
    When the task settles after its retries and queued continuations
    Then one learning pipeline runs against a frozen copy of that context
    And repeated settled events do not start another pipeline

  Scenario: Extension continuations do not train themselves
    Given only an extension-generated continuation has run
    When the agent settles
    Then automatic learning does not start

  Scenario: New settled tasks are coalesced while learning runs
    Given one learning pipeline is running
    When two further user tasks settle
    Then only the newest pending context runs after the current pipeline finishes
    And no two learning pipelines run concurrently

  Scenario: Disabling auto-memory consumes pending work
    Given auto-memory is disabled
    When a user task settles
    Then no learning pipeline starts
    And enabling auto-memory without another user task does not replay it
    And existing memory remains available to the model

  Scenario: Shutdown discards queued learning
    Given a learning pipeline is running and another is queued
    When the session shuts down
    Then the running child is cancelled and awaited
    And the queued context never starts

  Scenario: Learning failures are reported without an unhandled rejection
    Given a learning pipeline fails
    When its completion is observed
    Then the failure is reported once
    And a later user task can start learning again

  Scenario: Headless runs wait for learning receipts
    Given a user task runs in print or JSON mode with auto-memory enabled
    When the task settles
    Then the settled handler waits for the complete learning pipeline
    And the process does not exit before validation and receipts finish

  Scenario: Memory planning uses a package-owned minimal read-only agent
    Given automatic or manual memory consolidation starts its planner
    When the package launches the child Pi process
    Then the planner instructions come from the package-owned agents/memory-consolidator.md resource
    And the child disables extension, skill, prompt-template, context-file, and theme discovery
    And the child receives only read, grep, find, and ls tools
    And the parent remains the only process allowed to apply memory changes

  Scenario: Worker output closes before its exit event
    Given a headless learning worker has emitted its plan
    When both output pipes close before the worker exits
    Then the parent stays alive until the worker exit and receipt validation complete

  Scenario: New input while settings load belongs to the next task
    Given a task has settled and its settings read is pending
    When another user task begins before settings finish loading
    Then the first learning run sees only the first task's frozen context
    And the second task still triggers learning when it settles

  Scenario: The complete pipeline uses frozen context and released locks
    Given a settled task starts automatic memory learning
    When the live session changes while the memory planner runs
    Then the harness planner still receives the original task context
    And the memory phase releases its lock before harness planning starts
    And the headless settled handler returns after both phases finish
