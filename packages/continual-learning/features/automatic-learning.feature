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
    And selector, Memory, Harness, and AGENTS.md planner children may be running
    When the session shuts down
    Then every running child is cancelled and awaited
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

  Scenario: Memory planning uses mode-specific package-owned read-only prompts
    Given automatic or default manual Memory consolidation starts incrementally
    When the package launches the child Pi process
    Then the planner instructions come from the package-owned prompts/incremental-memory-consolidator.md resource
    And its typed builder binds every required identity value
    And its final plan contains only incremental identity fields, operations, and new Memory proposals
    But explicit full consolidation uses prompts/memory-consolidator.md
    And every child disables extension, skill, prompt-template, context-file, and theme discovery
    And the parent remains the only process allowed to expand, validate, and apply Memory changes

  Scenario: Worker output closes before its exit event
    Given a headless learning worker has emitted its plan
    When both output pipes close before the worker exits
    Then the parent stays alive until an observable worker-exit marker exists
    And receipt validation completes after that exit

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

  Scenario: Durable prohibition wording reaches Harness learning
    Given a settled user task states a durable prohibition using never, prohibit or prohibited, always block, don't or don’t
    Or it states an existing Chinese prohibition form
    When automatic learning screens the frozen context
    Then both durable Memory evidence and Harness constraint evidence are selected
    And unrelated uses of words such as blocked progress or a prohibition history remain screened out

  Scenario: Harness-only and AGENTS-only evidence bypasses Memory mutation
    Given an automatic task contains grounded Harness or AGENTS.md evidence but no durable Memory candidate
    When automatic learning runs
    Then no Memory planner or Memory mutation is required
    And the selector and each relevant later planner still run
    And the learning receipt records every attempted phase outcome

  Scenario: Later phases reuse the selector dossier without exploration
    Given the selector produced an authoritative dossier for the current task slice
    When Harness and AGENTS.md planning starts
    Then both planners receive that dossier path and the same task-slice snapshot
    And no model-backed explorer is called
    And neither planner performs repository-wide discovery

  Scenario: Shutdown awaits every concurrent later planner
    Given Harness and AGENTS.md planners are both running for one automatic task
    When session shutdown starts
    Then both child process groups are terminated
    And shutdown does not resolve until both close events are observed

  Scenario: Invalid incremental Memory output receives one small repair
    Given the incremental Memory planner returns parseable output rejected before mutation
    When the parent requests repair
    Then exactly one tool-free repair call receives only the rejected plan, bounded errors, selected names, and run identity
    And it receives no dossier body, snapshot path, Memory body, or repository path
    And the repaired delta is expanded before the existing validation and apply gates
    But a second rejection ends the phase without a full planner rerun

  Scenario: Live verification does not substitute fixtures for learning
    Given the explicit live smoke runs against disposable project and agent roots
    When the user requests a private preference and a durable Bash prohibition
    Then verification requires a learned flat rule in project harness.json and parent-owned receipts
    And missing or rejected learning fails the smoke instead of installing a replacement fixture
    And a separate runtime fixture checks scoped guidance and a harmless Bash result
    And every temporary file is removed after verification

  Scenario: Live verification isolates authentication from source files
    Given synthetic auth, model, and Memory model files in an explicit source agent directory
    When live verification prepares its disposable agent root
    Then auth and model files are private copies with mode 0600 and not symlinks
    And writing the child auth file never changes the source files

  Scenario: Receipts count applied Memory operations
    Given Memory planning creates or changes durable Memory
    When the parent validates and applies the plan
    Then the Memory attempt records the number of operations actually applied
    And failed or verified-noop later planner attempts remain present with zero applied operations
