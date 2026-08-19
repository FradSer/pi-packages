Feature: Agent Teams run-centric public API
  Agent Teams dispatches dependency-aware task graphs in a single call.
  Agents are declarative Markdown files (bundled, user, and project scopes);
  each run is a bounded set of child-process nodes reporting through one
  leader inbox fed by validated append-only worker outboxes. There are no
  peer mailboxes, no worker inboxes, and no leader-to-worker channel:
  upstream context travels through the DAG prompt at spawn time.

  Background:
    Given the pi-agent-teams-fradser extension is loaded

  Rule: Agents are declarative Markdown files

    Scenario: Discover agents from bundled, user, and project scopes
      When the leader queries agent definitions
      Then bundled agents shipped with the package are available
      And user agents under the Pi global agents directory are available
      And project agents under the project .pi/agents directory are available

    Scenario: Project agents override user and bundled agents with the same name
      Given an agent definition exists in multiple scopes
      When the leader resolves it by name
      Then the project scope wins over the user scope, and the user scope wins over the bundled scope

    Scenario: Agent frontmatter declares tools and model; the body is the role prompt
      Given an agent Markdown file with name, description, tools, and optional model frontmatter
      When the leader dispatches a task to that agent
      Then the worker receives the body as its role prompt
      And the worker receives exactly the declared execution tools plus its capability tools
      And a declared model is used when one is provided

    Scenario: Agent descriptions are injected into prompt guidance
      Given agent definitions exist in bundled, user, or project scopes
      When a turn starts and before_agent_start runs
      Then each discovered agent's name, description, scope, tools, and model are injected into prompt guidance

    Scenario: An unknown agent name fails the dispatch
      When the leader dispatches a task to an agent name that no scope defines
      Then the run is rejected before any worker starts and available agents are listed

  Rule: Leader prompt guidance is static per project

    Scenario: Prompt guidance does not embed live run status
      Given runs may be active in the session
      When before_agent_start builds the leader guidance
      Then it injects the orchestration protocol and the discovered agent definitions
      And it embeds no run ids, node statuses, or other per-turn live state
      And the guidance is byte-identical across turns while agents and cwd are unchanged
      And run awareness reaches the leader through tool results and completion follow-ups

  Rule: A run is a single-call DAG dispatch

    Scenario: Dispatch a single task in one call
      When the leader calls teammate_run with one task
      Then a run with one node is created
      And the node starts immediately
      And the run returns its run id and node status

    Scenario: Dispatch a dependency graph in one call
      When the leader calls teammate_run with tasks whose dependsOn edges form a DAG
      Then one run is created with all nodes and their dependency edges
      And root nodes start immediately
      And no worker starts before its dependencies complete

    Scenario: Downstream nodes auto-start after their dependencies complete
      Given a run whose nodes form a dependency chain
      When an upstream node completes
      Then the downstream node starts automatically without another leader call

    Scenario: Concurrency bounds simultaneous workers
      Given a run with more nodes than its concurrency limit
      When the run is dispatched
      Then at most the concurrency limit of nodes run at once
      And remaining ready nodes wait for a running slot

    Scenario: Teammates run in the background by default
      When the leader dispatches without setting background
      Then the tool call returns immediately with the run id
      And workers message team-leader with deliverables upon completion
      And one run-completion follow-up is delivered when the run settles
      When the leader dispatches with background=false
      Then the tool call blocks until the run reaches a terminal status and returns the node results

    Scenario: A long inline run detaches to background after the gather cap
      Given a background=false run is still executing after the foreground gather cap
      When the cap is exceeded
      Then the tool call returns with the run id instead of hanging the model turn
      And the run continues executing in the background
      And it delivers one run-completion follow-up when it settles

    Scenario: Multi-node runs synthesize a final summary by default
      Given a run is dispatched with more than one user task
      Then a summary node is appended after every leaf node unless summarize=false
      And it reads all node results and produces one synthesized final summary
      And the tool return shows that summary rather than per-node process text
      When a run has exactly one user task
      Then no summary node is added unless summarize=true

    Scenario: A run-level timeout fails the whole run
      Given a run declares a timeoutMs hard cap
      When the cap is exceeded while nodes are still running or pending
      Then the run is marked failed with a timeout error
      And pending nodes are cancelled
      And live workers are terminated

    Scenario: A collected run completion does not produce a duplicate follow-up
      Given a background run reaches a terminal status
      When the leader gathers its results with background=false
      Then the run-completion follow-up is suppressed for a gathered run

    Scenario: Read nodes with overlapping paths may run concurrently
      Given two ready nodes declare overlapping paths with access=read
      When the run dispatches them
      Then both nodes run in parallel

    Scenario: Write nodes with overlapping paths are blocked without worktree isolation
      Given a running write node declares a repo-relative path
      When the scheduler would start another write node with an equal, parent, or child path in the shared workspace
      Then that node is deferred until the overlapping node finishes
      And no two shared-workspace write nodes with overlapping paths run concurrently

    Scenario: Worktree isolation allows parallel write experiments
      Given a run with worktree=true
      When two write nodes overlap in paths
      Then each node runs in its own isolated worktree and may run concurrently
      And each node's diff is captured for integration review

    Scenario: A failed node fails the run and downstream nodes are not started
      Given a run whose node fails, times out, or is terminated by a signal
      When the run settles
      Then the run status is failed
      And no downstream node that depends on the failed node starts

    Scenario: Reject malformed task graphs
      When the leader dispatches a run with duplicate node ids, a dependsOn reference to an unknown node, or a dependency cycle
      Then the run is rejected before any worker starts

    Scenario: Reject ambiguous path ownership
      When the leader dispatches a node with a POSIX or Windows absolute path, parent traversal, glob, empty path list, or duplicate path
      Then the run is rejected before any worker starts

  Rule: Session resources are bounded

    Scenario: A session-wide cap bounds concurrent worker processes
      Given multiple runs are active in the same session
      When the scheduler starts nodes
      Then at most 8 worker child processes run at once across every run in the session
      And ready nodes beyond the cap wait for a session slot

    Scenario: Long task prompts spill to a temporary file that is removed on close
      Given a task description exceeds the inline argument limit
      When the spawner launches the worker
      Then the task is written to a private temporary file passed by reference
      And the temporary directory is removed when the child closes or fails to spawn

    Scenario: The shared state snapshot is persisted on transitions, not per stream delta
      Given workers are streaming live progress
      When the leader persists the shared state snapshot
      Then writes happen only when state actually changed since the last write
      And a poll tick with no changes performs no write

    Scenario: Background runs drain worker reports and enforce run timeouts
      Given a background run has a live worker and a run-level timeout
      When the scheduler starts the first worker
      Then the live poll starts without a foreground gather
      And worker outboxes are drained while the run is active
      And the run timeout terminates live workers and marks the run failed

    Scenario: Worker setup failures clean temporary task files and settle the node
      Given a long task prompt needs a temporary task file
      When temporary directory creation, task-file writing, or child spawning fails
      Then the temporary directory is removed
      And the node receives a failed terminal outcome instead of remaining running

  Rule: Run lifecycle is explicit

    Scenario: The leader coordinates only through dispatch, cancel, and retry
      Given background tasks are running
      When the leader inspects available tools
      Then no teammate_status, teammate_wait, teammate_message, or polling tool is registered for the leader
      And the leader waits for the worker message follow-up

    Scenario: Run completion is delivered automatically without a wait tool
      Given a background run is working
      When the run reaches a terminal status
      Then the harness delivers one completion follow-up to the leader
      And the follow-up includes the full final deliverable submitted by the worker
      And a single-node run delivers its result directly in the follow-up
      And no teammate_wait or teammate_status tool exists

    Scenario: The run summary follow-up carries no console navigation hint
      Given a run has settled
      When the leader receives the completion follow-up
      Then the summary covers status, nodes, and deliverables
      And the message does not include the /teammate console hint

    Scenario: Cancel a run stops its running nodes
      Given a run is working
      When the leader calls teammate_cancel with its run id
      Then running workers receive SIGTERM with a SIGKILL escalation after a bounded grace period
      And pending nodes are marked cancelled
      And the run is marked cancelled only after its workers close

    Scenario: Cancel one node while the rest of the run continues
      Given a run has multiple working nodes
      When the leader calls teammate_cancel with a node id
      Then that node is stopped and marked cancelled
      And its not-yet-started transitive dependents are cancelled
      And the remaining run nodes continue or settle normally

    Scenario: Retry failed and cancelled nodes without re-running completed ones
      Given a settled run has failed or cancelled nodes alongside completed nodes
      When the leader calls teammate_retry with its run id
      Then the failed and cancelled nodes reset to pending and re-dispatch
      And the completed nodes are retained
      And the run returns to running
      When the leader calls teammate_retry on a running run or with no failed nodes
      Then the operation is rejected

    Scenario: Runs do not survive session restarts
      Given a previous session recorded runs, nodes, and messages
      When a new or resumed session starts
      Then it starts with no runs
      And shutdown reports any worker that could not be confirmed closed before shared state is removed

  Rule: Messaging is capability-bound and leader-only

    Scenario: Workers report exclusively to the team leader
      Given a node is working
      When it calls teammate_message with a subject, body, and optional status
      Then the message is appended to the worker's own outbox
      And the leader validates the worker identity and spawn identity
      And the message is delivered to the single leader inbox
      And no recipient addressing exists on the worker tool

    Scenario: No peer or leader-to-worker channels exist
      When the shared state is inspected
      Then nodes carry no inbox and no sent-message transcript
      And the leader has no tool to message or broadcast to a worker
      And a worker's only inbound context is its task prompt with the DAG upstream handoff

    Scenario: Completing a node injects its result into downstream prompts
      Given a run has a node that other nodes depend on
      When that node completes
      Then no worker-to-worker mailbox handoff is written
      And each pending dependent's spawned prompt includes the upstream result

    Scenario: Messages carry no read receipts
      Given messages are delivered
      Then no message stores a read flag and no read receipt is exchanged

    Scenario: A worker delivers its outcome via teammate_message
      Given a node is working
      When it calls teammate_message with status="completed" or status="failed"
      Then the leader applies the report only to that node's current spawn
      And the report is delivered to the team leader

    Scenario: Intermediate worker communication does not interrupt the main session
      Given a worker sends a plan, progress report, or blocker to the team leader
      When the leader drains the worker outbox
      Then the message is recorded for the team leader
      And it does not interrupt the main session or trigger a model turn

    Scenario: The harness delivers one canonical terminal result per node
      Given a node exits normally, fails, times out, is cancelled, or never sends a terminal report
      When the child process close is observed
      Then the harness creates one canonical terminal result from node state and captured output
      And it records the result for the team leader
      And a worker terminal report alone is not treated as final delivery

    Scenario: Workers cannot access leader tools
      Given a worker is working
      When it tries to dispatch a run, cancel a run, retry a run, or mutate another node
      Then no such capability is available or the request is rejected

  Rule: Worker process outcomes are authoritative

    Scenario: A normal worker exit completes its node
      Given a worker reported a completed result
      When the child exits with code 0
      Then the node is completed and its result is retained
      And ready downstream nodes start

    Scenario: Worker children run with only the agent-teams extension
      Given a worker is spawned for a task
      When the child Pi process starts
      Then unrelated session extensions are disabled
      And the agent-teams worker extension is loaded explicitly
      So extension startup failures cannot consume the worker timeout

    Scenario: An abnormal worker exit fails its node
      Given a worker did not report a completed result
      When the child exits non-zero, times out, or is terminated by a signal
      Then the node is failed unless the leader cancelled it
      And downstream nodes are not started

    Scenario: A reported completion does not become a hard-timeout failure
      Given a worker reported completion but remains alive
      When the leader requests its graceful shutdown and observes SIGTERM close or timeout
      Then the node is retained as completed with the reported result

    Scenario: Completed run metadata is compacted safely
      Given a node run reached a final lifecycle outcome
      Then the leader persists the final state before removing its per-run outbox and replay metadata
      And an event from an old spawn cannot affect a newer spawn

  Rule: Invalid tool operations surface as Pi failures

    Scenario: Reject invalid leader and worker operations as tool failures
      Given a leader or worker invokes a capability outside its valid state or authorization
      When the operation cannot be completed
      Then the tool throws an error for Pi to record as a failed tool call

    Scenario: Inline foreground gather remains the explicit sync option
      Given the leader needs a run's result in the same turn
      When the leader calls teammate_run with background=false
      Then it blocks inline and detaches after the foreground cap
      And background runs never block the model turn

    Scenario: Legitimate empty and terminal data remains a normal result
      Given no agents or runs match a query, or a run has a terminal status
      When the leader queries that data
      Then the tool returns the data normally without throwing

  Rule: Console is a user interface, not an agent tool substitute

    Scenario: Console shows live teammate activity without intercepting global input
      Given a teammate is working
      When the user opens /teammate
      Then the full-screen console shows the teammate's live model text and current tool activity
      And working rows display a spinner with the live activity (current tool, reasoning, or text)
      And long tool activity is truncated inline with an ellipsis
      And a teammate widget row never wraps a truncation notice onto a second line
      And widget rows are left-padded to align with the native loader row
      And the idle widget stays hidden until a teammate is running
      And it does not intercept global terminal input

    Scenario: Detail scrolling preserves every wrapped display line
      Given a node detail has content longer than the terminal viewport
      When the user scrolls up, down, by page, jumps to either end, or uses the mouse wheel
      Then the viewport moves over wrapped display lines without omitting content
      And the footer shows the visible display-line range and available navigation keys
