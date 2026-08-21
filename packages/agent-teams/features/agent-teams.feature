Feature: Agent Teams run-centric orchestration and messaging contract
  Agent Teams dispatches dependency-aware task graphs in a single call.
  Agents are declarative Markdown files (bundled, user, and project scopes);
  each run is a bounded set of child-process nodes reporting through one
  leader inbox fed by validated append-only worker outboxes. There are no
  peer mailboxes, broadcasts, or worker inboxes, while the leader can steer
  a running RPC worker through teammate_message. Upstream context travels
  through the DAG prompt at spawn time.

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

    Scenario: A run can define and use an ephemeral reviewer agent
      Given the leader dispatches with ephemeralAgents containing name, prompt, tools, and optional model
      When a task refers to that ephemeral agent name
      Then the run is created and the task starts without writing any agent file
      And the worker receives the ephemeral prompt as its role prompt
      And the worker receives exactly the ephemeral tools plus its capability tools
      And an ephemeral agent shadows a bundled agent of the same name only for that run
      And a later run without that ephemeralAgents entry no longer resolves that name unless a file scope defines it
      And available-agents errors include ephemeral names when they exist
      And duplicate or reserved ephemeral agent names are rejected before any worker starts

  Rule: Leader prompt guidance is static per project

    Scenario: Prompt guidance does not embed live run status
      Given runs may be active in the session
      When before_agent_start builds the leader guidance
      Then it injects the orchestration protocol and the discovered agent definitions
      And it embeds no run ids, node statuses, or other per-turn live state
      And the guidance is byte-identical across turns while agents and cwd are unchanged
      And run awareness reaches the leader through tool results and teammate_message reports

  Rule: A run is a single-call DAG dispatch

    Scenario: Workers use turn budgets instead of wall-clock timeouts
      When the leader dispatches a task with a turnBudget
      Then the worker receives the turn budget in its prompt
      And no wall-clock timeout or deadline dimension exists in the run API

    Scenario: The default turn budget is high and only protects edge cases
      When the leader dispatches a task without a turnBudget
      Then the worker receives a default budget of at least 100 assistant turns
      And the leader may still provide a lower explicit turnBudget

    Scenario: Live tool execution remains visible between tool call and result events
      Given a worker has emitted a tool execution start event with its name and arguments
      When the worker progress parser processes the event stream
      Then the active tool includes the tool name and useful arguments
      And the active tool remains visible until the matching tool execution ends
      And the active tool is cleared after the execution ends

    Scenario: Parallel tool executions keep remaining activity visible
      Given two tool execution start events are active at the same time
      When one tool finishes before the other
      Then the remaining tool stays visible as the active tool
      And the active tool clears only after the final execution ends

    Scenario: Live reasoning reflects the latest assistant turn
      Given a worker has streamed reasoning in two assistant turns
      When the worker progress parser processes both turns
      Then the live reasoning contains the latest turn rather than the first turn

    Scenario: A completed worker may dynamically fan out child tasks
      Given a worker has published a bounded structured array output
      When the leader dispatches a bounded fanout
      Then each item becomes a separate validated child task
      And the fanout operation is registered for the leader

    Scenario: Fanout rejects invalid source output before spawning
      Given a completed node has no structured array output or exceeds the item limit
      When the leader calls teammate_fanout
      Then the operation fails before any child run is created

    Scenario: Fanout paths are advisory scheduling metadata
      Given a leader fans out child tasks with repository-relative paths
      When the child runs are created
      Then paths are scheduling and prompt metadata only
      And paths do not enforce read/write access or provide an OS or container sandbox

    Scenario: Input bindings resolve only declared dependency data
      Given a task binds an input from a dependency with an RFC-6901 JSON pointer
      When the dependent worker starts
      Then the named input is injected into its prompt
      And a binding to a non-dependency is rejected before spawning

    Scenario: Structured output is bounded before entering run state
      Given a worker reports structured output through teammate_message
      When the output exceeds the size or depth limit
      Then the output is rejected with a leader diagnostic
      And no unbounded value is stored on the node

    Scenario: Deeply nested structured output cannot break event draining
      Given a worker emits valid JSON deeper than the JavaScript call stack
      When the leader validates the structured output
      Then validation returns a bounded-output diagnostic instead of throwing
      And event draining continues normally

    Scenario: Named data flow and fork context stay explicit
      Given a task declares named fork context from upstream nodes
      When the dependent worker starts
      Then only the declared upstream data is injected

    Scenario: Runtime steer is delivered only through teammate_message
      Given a worker is running in RPC mode
      When the leader calls teammate_message with its run-qualified worker target and a body
      Then the message is written to the worker's steering stream
      And an ambiguous node id is rejected
      And the generated worker prompt permits leader steering in RPC mode
      And the prompt excludes peer mailboxes, broadcasts, and worker inboxes

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
      And one run-completion teammate_message report is delivered when the run settles
      When the leader dispatches with background=false
      Then the tool call blocks until the run reaches a terminal status and returns the node results

    Scenario: Background teammate_run suppresses startup text in tool return
      Given a task graph is dispatched in background mode
      When teammate_run executes
      Then the tool result suppresses the startup notice text
      And child workers are dispatched and report through follow-up messages

    Scenario: A long inline run detaches to background after the gather cap
      Given a background=false run is still executing after the foreground gather cap
      When the cap is exceeded
      Then the tool call returns with the run id instead of hanging the model turn
      And the run continues executing in the background
      And it delivers one run-completion teammate_message report when it settles

    Scenario: Multi-node runs synthesize a final summary by default
      Given a run is dispatched with more than one user task
      Then a summary node is appended after every leaf node unless summarize=false
      And it reads all node results and produces one synthesized final summary
      And the tool return shows that summary rather than per-node process text
      When a run has exactly one user task
      Then no summary node is added unless summarize=true

    Scenario: A collected run completion does not produce a duplicate teammate_message report
      Given a background run reaches a terminal status
      When the leader gathers its results with background=false
      Then the run-completion teammate_message report is suppressed for a gathered run

    Scenario: Nodes with overlapping paths run concurrently and coordinate through messaging
      Given two ready nodes declare overlapping paths
      When the run dispatches them
      Then both nodes run in parallel regardless of access
      And teammates coordinate shared-path access through teammate_message

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

    Scenario: Paths and access are scheduling metadata, not enforcement
      Given a task declares repository-relative paths and read or write access
      When the scheduler and worker prompt use those fields
      Then paths and access are scheduling and prompt metadata only
      And teammates that share paths coordinate through teammate_message
      And paths and access provide no OS or container sandbox
      And paths and access provide no true read/write enforcement

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

    Scenario: Background runs drain worker reports
      Given a background run has a live worker
      When the scheduler starts the first worker
      Then the live poll starts without a foreground gather
      And worker outboxes are drained while the run is active

    Scenario: Worker setup failures clean temporary task files and settle the node
      Given a long task prompt needs a temporary task file
      When temporary directory creation, task-file writing, or child spawning fails
      Then the temporary directory is removed
      And the node receives a failed terminal outcome instead of remaining running

    Scenario: Pre-spawn setup failures notify the leader immediately
      Given a background teammate cannot resolve its agent, state file, or worktree
      When the scheduler rejects the teammate before spawning a child process
      Then the leader receives one canonical terminal failure message
      And the leader receives one immediate teammate_message report
      And the run summary remains separate

  Rule: Run lifecycle is explicit

    Scenario: The leader coordinates through dispatch, runtime steer, cancel, and retry
      Given background tasks are running
      When the leader inspects available tools
      Then teammate_run, teammate_message, teammate_cancel, and teammate_retry are registered for the leader
      And no teammate_status, teammate_wait, or polling tool is registered
      And worker reports arrive through teammate_message

    Scenario: Each completed teammate notifies the leader immediately
      Given a background run has multiple working teammates
      When any teammate submits a completed or failed terminal report
      Then the worker's teammate_message report is delivered to the leader immediately
      And the report contains the full final deliverable
      And the remaining teammates continue running
      And each teammate delivers at most one terminal report

    Scenario: Automatic teammate follow-ups are serialized
      Given multiple worker reports arrive while the leader is idle or processing
      When the extension delivers reports to the leader
      Then reports are queued in arrival order
      And exactly one idle prompt reservation is active before agent start
      And later reports use the follow-up queue instead of starting another prompt
      And at most one user follow-up is submitted at a time
      And no "Agent is already processing a prompt" runtime error is generated
      When agent_settled fires
      Then the next pending batch starts only once

    Scenario: An unrelated agent start does not consume a queued teammate report
      Given an automatic teammate report is waiting for its matching before_agent_start event
      When an unrelated agent_start event fires
      Then the teammate report remains active and is not dropped
      And the report is released only after its matching before_agent_start and agent_start events

    Scenario: A failed automatic follow-up preserves reports and retries with backoff
      Given an automatic teammate report is dispatched through the void Pi API
      When the API fails before agent_start
      Then the report batch is restored to the front of the queue
      And the reservation is released
      And retry scheduling uses a delay instead of a busy loop

    Scenario: Follow-up retries stop at a bounded attempt count
      Given an automatic teammate report repeatedly fails before agent_start
      When the configured maximum retry attempts are exhausted
      Then the report is moved to a dead-letter result
      And no further retry timer is scheduled

    Scenario: Follow-up retry attempts are scoped to each report batch
      Given one automatic teammate report exhausts its retry attempts
      When an unrelated later report is dispatched
      Then the later report receives its own maximum retry attempt budget

    Scenario: Follow-up watchdog and retry timers are cleaned up at lifecycle boundaries
      Given an automatic teammate report is dispatched through the void Pi API
      When the queue is reset before a retry delay expires
      Then the retry timer is cancelled and cannot keep the child process alive
      When another report reaches agent_start and agent_settled during dispatch
      Then no watchdog timer remains armed after successful settlement
      And the child process can exit without waiting for the watchdog delay

    Scenario: A delayed follow-up cannot cross a session boundary
      Given an automatic teammate report has a pending dispatch timer
      When the current session shuts down before the timer fires
      Then the timer is cancelled or ignored
      And the report is not delivered to the replacement session

    Scenario: Run completion is delivered automatically without a wait tool
      Given a background run is working
      When the run reaches a terminal status
      Then the worker's teammate_message reports are available to the leader
      And each report includes the full final deliverable submitted by the worker
      And a single-node run delivers its result directly through teammate_message
      And no teammate_wait or teammate_status tool exists

    Scenario: Automatic teammate follow-ups are readable to the leader
      Given queued teammate reports contain internal run identifiers
      When the reports are delivered as one follow-up
      Then the follow-up omits run identifiers and protocol labels
      And each worker report is wrapped in an `<agent-message from="<teammate>">` marker
      And the teammate identity is used instead of the shared agent role name
      And the worker's full report appears inside that marker
      And canonical terminal bodies omit internal run and node prefixes
      And each worker report's transport content contains only its `<agent-message from="<agent>">` wrapper and full deliverable
      And the worker report transport content does not include a `Run [<run>]` summary
      And the worker report transport content does not include "Teammate @<teammate> finished."
      And each terminal worker report renders a separate system completion line "Teammate @<teammate> finished."
      And only the agent name in the marker is rendered with the stable theme color

    Scenario: Agent reports use a distinct transcript renderer
      Given an automatic agent report is delivered as a custom message
      When the transcript renders the report in its collapsed state
      Then it shows a bold [Agent message] label followed by `from @<teammate>`
      And it shows an expand hint instead of the full report body
      When the report is expanded
      Then the full report body is rendered with the custom message text style
      And the completion notice is rendered separately from the report body

    Scenario: The run summary teammate_message carries no console navigation hint
      Given a run has settled
      When the leader receives the completion teammate_message
      Then the summary covers status, nodes, and deliverables
      And the message does not include the /teammate console hint

    Scenario: Cancel a run stops its running nodes
      Given a run is working
      When the leader calls teammate_cancel with its run id
      Then running workers receive SIGTERM with a SIGKILL escalation after a bounded grace period
      And pending nodes are marked cancelled
      And the run remains non-terminal until every running worker closes
      And the run is marked cancelled only after its workers close

    Scenario: Partial cancellation cannot be overwritten by completed nodes
      Given one node has reported completion while another node is still running
      When the leader cancels the run
      Then cancelRequested is recorded before any worker close is finalized
      And the run remains non-terminal while the running child is open
      And the final run status is cancelled rather than completed

    Scenario: Cancellation intent wins when termination sees an exited child
      Given cancellation has begun for a worker whose exit code is set before its close event
      When terminateWorker reports that no signal was sent
      Then the pending close finalizer still records cancellation
      And normal close finalization cannot overwrite the cancelled node or run

    Scenario: Close observation before onExit preserves node-only cancellation
      Given a node cancellation request is recorded before the child close event
      When the close-observation listener runs before the run-machine onExit callback
      Then CancellationIntents.close retains the requested cancellation until the deferred finalizer is registered
      And the node settles as cancelled rather than completed or failed
      And a node-only cancellation does not cancel the rest of the run

    Scenario: Late close callbacks are harmless after shutdown
      Given shutdown invalidates the current run-machine generation before a worker close callback runs
      When the late close callback is delivered
      Then the callback cannot mutate cleared run-machine state
      And shutdown diagnostics retain any worker that was not confirmed closed

    Scenario: A terminal worker report does not release process resources early
      Given a worker has sent a completed or failed report but its child process is still open
      When the leader schedules the run
      Then the worker still consumes a session worker slot
      And overlapping shared-workspace writes remain blocked
      And downstream dependencies do not start
      When the child process close is observed
      Then the slot and write conflict are released
      And downstream dependencies may start

    Scenario: Each worker spawn accepts only one terminal report
      Given a worker spawn has accepted a completed or failed report
      When the same spawn sends another terminal report with a different event id
      Then the later terminal report is discarded as a stale diagnostic
      And it does not create another terminal mailbox delivery

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

    Scenario: Shutdown confirms workers only after close is observed
      Given a worker has an exit code or signal but no observed close event
      When the session shuts down
      Then the worker is not reported as confirmed closed
      And confirmed closed means the child close event was observed
      And its registry entry is retained until close is observed
      And a late close callback cannot mutate cleared run-machine state

    Scenario: Terminal session state is bounded without removing active runs
      Given the session has more terminal runs than the retention limit and one active run
      When terminal state compaction runs
      Then the oldest terminal runs are removed
      And the newest terminal runs are retained
      And the active run remains present
      And the leader mailbox retains only its newest bounded messages

    Scenario: Worktree finalization failures still settle the node
      Given a worker process has closed in an isolated worktree
      When capturing the worktree diff raises an error
      Then the node receives a failed terminal outcome with the capture diagnostic
      And worktree cleanup runs in a finally path

    Scenario: Shutdown preserves diagnostics for unconfirmed workers
      Given shutdown cannot confirm that a worker child closed
      When the session state is removed
      Then the leader receives a shutdown diagnostic naming that worker

    Scenario: Malformed worker output becomes a leader diagnostic
      Given a worker outbox contains malformed structured output
      When the leader drains the outbox
      Then the malformed output is consumed once
      And a diagnostic is delivered to the leader

  Rule: Messaging is capability-bound and leader-only

    Scenario: Workers report exclusively to the team leader
      Given a node is working
      When it calls teammate_message with a subject, body, and optional status
      Then the message is appended to the worker's own outbox
      And the leader validates the worker identity and spawn identity
      And the message is delivered to the single leader inbox
      And no recipient addressing exists on the worker tool

    Scenario: No peer mailboxes, broadcasts, or worker inboxes exist
      When the shared state is inspected
      Then nodes carry no inbox and no sent-message transcript
      And no peer mailbox, broadcast, or worker inbox operation is available
      And the leader can steer a running RPC worker through teammate_message
      And a worker's only other inbound context is its task prompt with the DAG upstream handoff

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
      And the leader receives the report through the native teammate_message follow-up

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
      So extension startup failures cannot consume the worker turn budget

    Scenario: An abnormal worker exit fails its node
      Given a worker did not report a completed result
      When the child exits non-zero, times out, or is terminated by a signal
      Then the node is failed unless the leader cancelled it
      And downstream nodes are not started

    Scenario: A reported completion remains completed during graceful shutdown
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

    Scenario: Teammate widget rows use the agent-name activity format
      Given a teammate has a task name, agent name, and live activity
      When the passive widget renders its row
      Then the row is formatted as "agent name · current activity"
      And the task id is not rendered in the passive row
      And the spinner and agent name appear before the separator
      And a worker without live activity shows "Working..." after the separator
      And long tool activity is truncated inline with an ellipsis
      And a teammate widget row never wraps a truncation notice onto a second line
      And widget rows start with one left-padded pi-kit spinner frame aligned with the native loader row
      And each row shows the colored agent identity before the separator and bold live activity after it
      And each running agent uses a visible stable theme color (success, warning, error, or link) for its identity
      And the idle widget stays hidden until a teammate is running
      And it does not intercept global terminal input

    Scenario: Teammate activity adapts to the available widget width
      Given a teammate has a long tool command and a narrow or wide widget
      When the passive widget renders its row
      Then the full live activity is retained until the renderer applies the available width
      And the activity truncation width accounts for the spinner, agent name, and separator
      And the row remains a single line at every supported width
      And a narrow widget truncates the agent identity before sacrificing the activity label
      And a missing activity shows "Working..." only when no live tool, reasoning, or text exists

    Scenario: Markdown in live teammate activity is rendered instead of shown literally
      Given a teammate's live activity is `**Inspecting unused variable in report code**`
      When the passive widget renders the teammate row
      Then Markdown emphasis is rendered in the activity
      And the row does not show literal `**` markers

    Scenario: Teammate widget adapts live activity to available width without wrapping
      Given a running teammate has active tool, thinking, or text activity
      When the passive widget renders with wide or narrow terminal width
      Then the activity text adapts to the remaining line width instead of a fixed character cap
      And active tool execution takes priority over live thinking and live text
      And live thinking or text falls back to the latest non-empty content
      And a worker without any live activity shows "Working..."
      And each teammate row is strictly a single line without wrapping even in narrow terminals

    Scenario: Finished tool activity does not remain the current activity
      Given a worker has streamed a tool call followed by new thinking or text
      When the live worker progress is rendered
      Then the widget shows the new thinking or text instead of the finished tool label
      And the detail view does not label the finished tool as current

    Scenario: Detail scrolling reserves space for console chrome
      Given a node detail has content longer than the terminal viewport
      When the detail console calculates its body viewport
      Then the top border, header, spacing, footer, and bottom border remain visible
      And the viewport does not request more body lines than the terminal can render

    Scenario: Detail scrolling preserves every wrapped display line
      Given a node detail has content longer than the terminal viewport
      When the user scrolls up, down, by page, jumps to either end, or uses the mouse wheel
      Then the viewport moves over wrapped display lines without omitting content
      And the footer shows the visible display-line range and available navigation keys

  Rule: Shared worker runtime owns process identity and configured user paths

    Scenario: User-scoped agent state honors the configured Pi agent directory
      Given PI_CODING_AGENT_DIR points to a custom agent directory
      When the leader discovers user agents or writes run state
      Then it reads and writes below that configured directory
      And it does not reconstruct ~/.pi/agent directly

    Scenario: Worker cancellation observes close before finalizing a run
      Given a worker ignores the first termination signal
      When the leader cancels the worker
      Then termination escalates only after the grace period
      And run finalization waits for the worker close event
