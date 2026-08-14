Feature: Agent Teams public API
  Agent Teams keeps reusable teammate identities only for the current session.
  Each task run is a bounded child process, while an idle teammate remains
  available for follow-up work until its mailbox is clear and its idle TTL expires.

  Background:
    Given the @fradser/pi-agent-teams extension is loaded

  Rule: Teammates are reusable current-session executors

    Scenario: Register a teammate with an executable role
      When the leader calls teammate_register with a worker, reviewer, specialist, or observer role
      Then the teammate is registered with its reusable prompt
      And team-leader is not a registerable teammate role

    Scenario: Configure an existing teammate
      Given a teammate is registered
      When the leader calls teammate_configure with one or more configuration fields
      Then its description, prompt, model, or tools are updated
      And a running worker keeps the configuration it started with

    Scenario: Reuse a compatible idle teammate
      Given an idle teammate has matching role, prompt, model, and tools
      When the leader needs another task of that kind
      Then the leader reuses that teammate instead of registering a duplicate
      And the next task receives a fresh worker run identity

    Scenario: Do not silently reuse a materially different teammate
      Given an idle teammate differs in its role prompt, model, or tools
      When the leader registers a teammate for the new configuration
      Then a distinct teammate is registered

    Scenario: Retire only a truly expired teammate
      Given a teammate is idle with no assigned or working task and no unread messages
      When it remains idle for the configured TTL
      Then the teammate record and mailbox are removed automatically
      And its terminal task results remain available for synthesis

    Scenario: Keep an idle teammate with pending communication
      Given a teammate is idle with an unread mailbox message
      When its idle TTL expires
      Then it is retained until the message is consumed or removed

    Scenario: Retain a reported terminal task until its worker closes
      Given a worker reported a terminal task status while its process is still running
      When the leader cleans up terminal tasks
      Then the task and teammate remain until the worker close is recorded

    Scenario: Remove only an idle teammate
      Given a teammate is idle
      When the leader calls teammate_remove
      Then its teammate record and mailbox are removed

    Scenario: Do not restore a prior session's team
      Given a previous session recorded teammates, tasks, and messages
      When a new or resumed session starts
      Then it starts with an empty team
      And shutdown reports any worker that could not be confirmed closed before shared state is removed

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

  Rule: Tasks declare scopes and access before they run

    Scenario: Create and assign a task in one action
      Given a teammate is registered
      When the leader calls teammate_create_task with assignee, title, description, repo-relative paths, read or write access, and optional blockedBy IDs
      Then one assigned task is created
      And the assignee receives a task message
      And inverse dependency edges are derived internally

    Scenario: Partition a parallel team before it starts
      Given multiple teammates will work in parallel
      When the leader defines a distinct outcome, repo-relative paths, and access mode for every task
      Then the task board records that coordination context before any worker starts

    Scenario: Allow overlapping read scopes
      Given a working read task has a repo-relative path
      When the leader starts another ready read task for the same path
      Then both tasks may run in parallel

    Scenario: Block unsafe overlapping writes in a shared workspace
      Given a working write task has a repo-relative path
      When the leader starts another ready write task for an equal, parent, or child path without worktree isolation
      Then the operation is rejected before the second worker starts
      And the leader can sequence the tasks or use isolated worktrees with integration review

    Scenario: Allow isolated overlapping write experiments
      Given a working write task has a repo-relative path
      When the leader starts another ready write task for the same path in a worktree
      Then the task starts with an integration-review warning
      And the two worker processes do not share a working directory

    Scenario: Reject ambiguous path ownership
      When the leader creates a task with a POSIX or Windows absolute path, parent traversal, glob, empty path list, or duplicate path
      Then the operation is rejected before a teammate receives work

    Scenario: Queue follow-up work for the same teammate
      Given a teammate already owns a task
      When the leader creates a later task for that teammate
      Then the task remains assigned until the teammate becomes idle
      And no second worker run starts for that teammate concurrently

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

    Scenario: Retry failed work with a fresh run
      Given a worker failed a task and its teammate is idle
      When the leader calls teammate_start_task with retry=true
      Then its prior result, error, and run details are cleared
      And the same teammate begins a fresh run identity

    Scenario: Wait only when a result is needed
      Given independent task runs are working
      When the leader calls teammate_wait with their task IDs
      Then it is the explicit gather barrier
      And it returns each task's terminal status and result

    Scenario: Cancel a task run only after its worker closes
      Given a task is working
      When the leader calls teammate_cancel_task
      Then the leader records cancellation intent for that run before awaiting its close event
      And its worker receives SIGTERM
      And a SIGTERM-cooperative worker that exits 0 is not recorded completed or failed before cancellation
      And a SIGTERM-resistant worker receives SIGKILL after a bounded grace period
      And the task remains non-terminal until the worker close is observed
      And only then is the task marked cancelled and its run lifecycle leaves working
      And cancellation intent is cleared after the cancellation attempt finishes

    Scenario: Refuse to cancel a restored task without a live child process
      Given a restored task is working but its child process is unavailable
      When the leader calls teammate_cancel_task
      Then the tool fails without marking the task cancelled

  Rule: Messaging is symmetric, proactive, and capability-bound

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
      And the report is delivered to the main session inbox

    Scenario: Intermediate worker communication stays in the mailbox
      Given a worker sends a plan, progress report, blocker, or direct message to agent
      When the leader drains the worker outbox
      Then the message is recorded in the agent mailbox
      And it does not interrupt the main session or trigger a model turn
      And the leader can retrieve it with teammate_inbox

    Scenario: The harness delivers every terminal result to the main session
      Given a worker exits normally, fails, times out, is cancelled, or never sends a terminal report
      When the child process close is observed
      Then the harness creates one canonical terminal result from task state and captured output
      And it injects that result into the main session as one follow-up update
      And it records the same result in the agent mailbox

    Scenario: A worker terminal report is not treated as final delivery
      Given a worker sent a completed or failed teammate_report
      When the child process has not closed yet
      Then the main session does not receive a terminal follow-up yet
      And the close handler remains responsible for the one authoritative terminal result

    Scenario: Task start does not interrupt the main session
      Given the leader starts a teammate task
      When the child process is spawned
      Then the task board records the running task
      And the main session remains focused on dispatch and final results

    Scenario: Workers cannot broadcast or mutate the board
      Given a worker is working
      When it tries to broadcast, configure a teammate, create a task, start a task, cancel a task, or mutate another task
      Then no such capability is available or the request is rejected

  Rule: Worker process outcomes are authoritative

    Scenario: A normal worker exit completes its task
      Given a worker reported a completed result
      When the child exits with code 0
      Then the task is completed and its result is retained

    Scenario: A worker process exits after its assigned task
      Given a worker completed or failed its assigned task
      When it reports the final outcome to the leader
      Then that child process exits instead of watching its mailbox for future work
      And its idle teammate identity remains available for a later task
    Scenario: An abnormal worker exit fails its task
      Given a worker reported a completed result
      When the child exits non-zero, times out, or is terminated by a signal
      Then the task is failed unless the leader cancelled it
      And downstream tasks are not notified as ready

    Scenario: Completed run metadata is compacted safely
      Given a worker run reached a final lifecycle outcome
      Then the leader persists the final board before removing its per-run outbox and replay metadata
      And an event from an old run cannot affect a new run

  Rule: Invalid tool operations surface as Pi failures

    Scenario: Reject invalid leader and worker operations as tool failures
      Given a leader or worker invokes a capability outside its valid state or authorization
      When the operation cannot be completed
      Then the tool throws an error for Pi to record as a failed tool call
      And it does not return an ignored isError result field

    Scenario: Cancelled or timed-out waits surface as tool failures
      Given the leader is waiting for task results
      When the wait is cancelled or exceeds its timeout
      Then teammate_wait throws an error

    Scenario: Legitimate empty and terminal data remains a normal result
      Given no teammates or tasks match a list query, or a task has a terminal status
      When the leader lists that data
      Then the tool returns the data normally without throwing

  Rule: Console is a user interface, not an agent tool substitute

    Scenario: Team console stays display-focused
      Given a team exists
      When the user opens /teammate
      Then the full-screen console shows members, tasks, and mailbox history
      And working rows display a spinner and working...
      And it does not intercept global terminal input
