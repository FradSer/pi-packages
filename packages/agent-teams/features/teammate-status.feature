Feature: Agent Teams public API
  Agent Teams separates persistent teammate configuration, task definitions,
  task runs, and messages. The main session is always the leader; workers only
  receive message, inbox, and report capabilities.

  Background:
    Given the @fradser/pi-agent-teams extension is loaded

  Rule: Teammate configuration is a persistent resource

    Scenario: Register a teammate with an executable role
      When the leader calls teammate_register with a worker, reviewer, specialist, or observer role
      Then the teammate is registered with its reusable prompt
      And team-leader is not a registerable teammate role

    Scenario: Configure an existing teammate
      Given a teammate is registered
      When the leader calls teammate_configure with one or more configuration fields
      Then its description, prompt, model, or tools are updated
      And a running worker keeps the configuration it started with

    Scenario: Remove only an idle teammate
      Given a teammate is idle
      When the leader calls teammate_remove
      Then its teammate record and mailbox are removed

    Scenario: Refuse to remove a teammate with active work
      Given a teammate is working or has an assigned task
      When the leader calls teammate_remove
      Then the operation is rejected
      And the leader must cancel or complete its active work before removing the teammate

    Scenario: Roles receive least-privilege default execution tools
      Given a teammate was registered without an explicit tools list
      When the leader starts its task
      Then worker defaults include read, bash, edit, and write
      And reviewer and specialist defaults exclude edit and write
      And observer defaults exclude bash, edit, and write

    Scenario: Explicit teammate tools override role defaults
      Given a teammate was registered or configured with an explicit tools list
      When the leader starts its task
      Then that worker receives exactly those execution tools plus its three capability tools

  Rule: Tasks are immutable definitions until their run starts

    Scenario: Create and assign a task in one action
      Given a teammate is registered
      When the leader calls teammate_create_task with assignee, title, description, and optional blockedBy IDs
      Then one assigned task is created
      And the assignee receives a task message
      And inverse dependency edges are derived internally

    Scenario: Task dependency direction is not publicly mutable
      When the leader inspects the available tools
      Then no public tool accepts blocks
      And no public task-dependency mutation tool is available

    Scenario: List task definitions and run state
      Given tasks exist
      When the leader calls teammate_list_tasks
      Then it can filter by status or assignee
      And each result includes its task state and any run lifecycle information

  Rule: A task run is explicit and never blocks the leader

    Scenario: Start a ready assigned task
      Given an assigned task whose dependencies are complete
      When the leader calls teammate_start_task with its task ID
      Then a new run identity and child process are created
      And the tool returns immediately
      And the main session remains free to coordinate

    Scenario: Refuse to start a blocked, terminal, or already-running task
      Given a task that is blocked, completed, cancelled, or already working
      When the leader calls teammate_start_task
      Then the operation is rejected without creating another run

    Scenario: Retry a failed task explicitly
      Given a task failed in an earlier run
      When the leader calls teammate_start_task with retry=true
      Then its prior result, error, and run details are cleared
      And it begins with a fresh run identity

    Scenario: Do not retry implicitly
      Given a task failed in an earlier run
      When the leader calls teammate_start_task without retry=true
      Then the operation is rejected

    Scenario: Wait only when a result is needed
      Given independent task runs are working
      When the leader calls teammate_wait with their task IDs
      Then it is the explicit gather barrier
      And it returns each task's terminal status and result

    Scenario: Cancel a task run
      Given a task is working
      When the leader calls teammate_cancel_task
      Then the task remains cancelled
      And its worker receives SIGTERM
      And the run lifecycle eventually leaves working

  Rule: Messaging is symmetric and capability-bound

    Scenario: The leader sends a direct message
      Given a teammate is registered
      When the leader calls teammate_message with its name
      Then the message is published to that teammate inbox

    Scenario: The leader broadcasts through the same message tool
      Given multiple teammates are registered
      When the leader calls teammate_message with to="all" and an optional role filter
      Then every selected teammate receives the message

    Scenario: A worker messages a peer or the main session
      Given a worker is working
      When it calls teammate_message with a peer name or to="agent"
      Then the leader validates worker identity, run identity, and recipient
      And the message reaches the selected inbox

    Scenario: Inbox reads are scoped to the caller
      Given messages are present
      When the main session calls teammate_inbox
      Then it reads the agent inbox into the current conversation
      When a worker calls teammate_inbox
      Then it reads only its own inbox and emits read receipts

    Scenario: A worker reports only its bound task run
      Given a worker is working a task
      When it calls teammate_report with progress, completion, or failure
      Then the leader applies the report only to that worker's current task and run

    Scenario: Workers cannot broadcast or mutate the board
      Given a worker is working
      When it tries to broadcast, configure a teammate, create a task, start a task, cancel a task, or mutate another task
      Then no such capability is available or the request is rejected

  Rule: Worker process outcomes are authoritative

    Scenario: A normal worker exit completes its task
      Given a worker reported a completed result
      When the child exits with code 0
      Then the task is completed and its result is retained

    Scenario: An abnormal worker exit fails its task
      Given a worker reported a completed result
      When the child exits non-zero, times out, or is terminated by a signal
      Then the task is failed unless the leader cancelled it
      And downstream tasks are not notified as ready

    Scenario: Completed run metadata is compacted safely
      Given a worker run reached a final lifecycle outcome
      Then the leader persists the final board before removing its per-run outbox and replay metadata
      And an event from an old run cannot affect a new run

  Rule: Console is a user interface, not an agent tool substitute

    Scenario: Team console stays display-focused
      Given a team exists
      When the user opens /teammate
      Then the full-screen console shows members, tasks, and mailbox history
      And working rows display a spinner and working...
      And it does not intercept global terminal input
