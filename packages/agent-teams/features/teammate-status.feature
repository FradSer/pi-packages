Feature: Agent Teams run-centric public API
  Agent Teams dispatches dependency-aware task graphs in a single call.
  Agents are declarative Markdown files (bundled, user, and project scopes);
  each run is a bounded set of child-process nodes with a best-effort mailbox
  (validated delivery, no read receipts) and per-spawn identity validation.

  Background:
    Given the @fradser/pi-agent-teams extension is loaded

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

    Scenario: Agent descriptions are the routing contract
      Given agent definitions are discovered
      When the leader lists available agents
      Then each entry shows its name, description, scope, tools, and model so the leader can route work

    Scenario: An unknown agent name fails the dispatch
      When the leader dispatches a task to an agent name that no scope defines
      Then the run is rejected before any worker starts

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

    Scenario: Foreground dispatch gathers results; background dispatch returns immediately
      When the leader dispatches with background=false (default)
      Then the tool call blocks until the run reaches a terminal status and returns the node results
      When the leader dispatches with background=true
      Then the tool call returns immediately with the run id
      And one run-completion follow-up is delivered when the run settles

    Scenario: A long foreground run detaches to background after the foreground cap
      Given a foreground run is still executing after the foreground gather cap
      When the cap is exceeded
      Then the tool call returns with the run id instead of hanging the model turn
      And the run continues executing in the background
      And it delivers one run-completion follow-up when it settles

    Scenario: An optional summary node synthesizes the run instead of truncating node output
      Given a run is dispatched with summarize=true
      Then a summary node is appended after every leaf node
      And it reads all node results and produces one synthesized final summary
      And the tool return shows that summary rather than truncated per-node output
      When summarize is not set
      Then the tool return lists node statuses only and points to teammate_status/teammate_inbox for detail

    Scenario: A run-level timeout fails the whole run
      Given a run declares a timeoutMs hard cap
      When the cap is exceeded while nodes are still running or pending
      Then the run is marked failed with a timeout error
      And pending nodes are cancelled
      And live workers are terminated

    Scenario: A collected run completion does not produce a duplicate follow-up
      Given a background run reaches a terminal status
      When the leader collects its results with teammate_wait or foreground gather
      Then the run-completion follow-up is suppressed

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

  Rule: Run lifecycle is explicit

    Scenario: Status lists agents, runs, and node detail
      Given runs exist
      When the leader calls teammate_status
      Then it returns discovered agents and a run overview
      When the leader calls teammate_status with a run id
      Then it returns that run's nodes with status, spawn lifecycle, and results

    Scenario: Wait is the explicit gather barrier for runs
      Given a background run is working
      When the leader calls teammate_wait with its run id
      Then it returns each run's terminal status and node results

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

    Scenario: Cleanup prunes terminal runs
      Given terminal runs exist
      When the leader calls teammate_cleanup
      Then terminal runs and their node mailboxes are removed
      And running and pending runs are retained

    Scenario: Runs do not survive session restarts
      Given a previous session recorded runs, nodes, and messages
      When a new or resumed session starts
      Then it starts with no runs
      And shutdown reports any worker that could not be confirmed closed before shared state is removed

  Rule: Messaging is capability-bound

    Scenario: A worker messages the main session only
      Given a node is working
      When it calls teammate_message with to="agent"
      Then the leader validates the worker identity and spawn identity
      And the message reaches the agent inbox
      When it tries to message a peer node key
      Then the request is rejected and no peer message is queued

    Scenario: Inbox reads are scoped to the caller
      Given messages are present
      When the main session calls teammate_inbox
      Then it reads the agent inbox into the current conversation
      When a worker calls teammate_inbox
      Then it reads only its own node inbox without exchanging read receipts
      And the inbox tool exposes only an unreadOnly option

    Scenario: A worker reports only its bound node
      Given a node is working
      When it calls teammate_report with progress, completion, or failure
      Then the leader applies the report only to that node's current spawn
      And the report is delivered to the main session inbox

    Scenario: Intermediate worker communication stays in the mailbox
      Given a worker sends a plan, progress report, blocker, or direct message to agent
      When the leader drains the worker outbox
      Then the message is recorded in the agent mailbox
      And it does not interrupt the main session or trigger a model turn
      And the leader can retrieve it with teammate_inbox

    Scenario: The harness delivers one canonical terminal result per node
      Given a node exits normally, fails, times out, is cancelled, or never sends a terminal report
      When the child process close is observed
      Then the harness creates one canonical terminal result from node state and captured output
      And it records the result in the agent mailbox
      And a worker terminal report alone is not treated as final delivery

    Scenario: Workers cannot access leader tools
      Given a worker is working
      When it tries to broadcast, dispatch a run, cancel a run, or mutate another node
      Then no such capability is available or the request is rejected

  Rule: Worker process outcomes are authoritative

    Scenario: A normal worker exit completes its node
      Given a worker reported a completed result
      When the child exits with code 0
      Then the node is completed and its result is retained
      And ready downstream nodes start

    Scenario: An abnormal worker exit fails its node
      Given a worker reported a completed result
      When the child exits non-zero, times out, or is terminated by a signal
      Then the node is failed unless the leader cancelled it
      And downstream nodes are not started

    Scenario: A reported completion does not become a hard-timeout failure
      Given a worker reported completion but remains alive
      When the leader requests its graceful shutdown and observes SIGTERM close
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

    Scenario: Cancelled or timed-out waits surface as tool failures
      Given the leader is waiting for run results
      When the wait is cancelled or exceeds its timeout
      Then teammate_wait throws an error

    Scenario: Legitimate empty and terminal data remains a normal result
      Given no agents or runs match a query, or a run has a terminal status
      When the leader queries that data
      Then the tool returns the data normally without throwing

  Rule: Console is a user interface, not an agent tool substitute

    Scenario: Console shows live node activity without intercepting global input
      Given a run node is working
      When the user opens /teammate
      Then the full-screen console shows the node's live model text and current tool activity
      And working rows display a spinner and working...
      And it does not intercept global terminal input

    Scenario: Detail scrolling preserves every wrapped display line
      Given a node detail has content longer than the terminal viewport
      When the user scrolls up, down, by page, or jumps to either end
      Then the viewport moves over wrapped display lines without omitting content
      And the footer shows the visible display-line range and available navigation keys
