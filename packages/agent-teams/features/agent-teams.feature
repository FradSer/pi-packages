Feature: Agent Teams collaborative organization contract
  Agent Teams gives Pi a Claude-Code-style team layer: named resident
  teammates, a shared local task board with self-claim, and peer-to-peer
  messaging between teammates. Agents are declarative Markdown files
  (bundled, user, project, and project-local scopes). The team leader spawns named
  teammates as long-lived child Pi processes in RPC mode; idle teammates
  are woken by harness polling (inbox delivery and claimable-task
  notices), never by leader-model busywork. Task completion is gated by
  deterministic verify commands; peer traffic never enters the leader's
  model context.

  Background:
    Given the pi-agent-teams-fradser extension is loaded

  Rule: Agents are declarative Markdown files

    Scenario: Discover agents from bundled, user, project, and project-local scopes
      When the leader queries agent definitions
      Then bundled agents shipped with the package are available
      And user agents under the Pi global agents directory are available
      And project agents under the project .pi/agents directory are available

    Scenario: xxx.local.md files mark personal overrides inside .pi/agents
      Given a definition file named example.local.md sits next to example.md in the project agents directory
      Then example.local.md is discovered as project-local scope and never git-managed
      And example.md is discovered as project scope and marked git-managed

    Scenario: Project scopes distinguish git-managed from local definitions
      Given an agent definition exists as name.md in a git-managed repository's agents directory
      Then that definition is marked git-managed
      And name.local.md definitions are marked local and never enter version control by convention

    Scenario: Local override files dedupe against their shared counterpart by teammate name
      Given both dup.md and dup.local.md exist in the project agents directory with the same frontmatter name
      When the leader resolves that name
      Then exactly one definition is returned, from the project-local scope
      And the discovery map contains no duplicate entry for that name

    Scenario: Agent frontmatter declares tools, model, verify, and worktree; the body is the role prompt
      Given an agent Markdown file with name, description, tools, model, optional verify, and optional worktree frontmatter
      When the leader spawns a teammate with that agent
      Then the teammate receives the body as its role prompt
      And the teammate receives exactly the declared execution tools plus its capability tools
      And a declared model is used when one is provided
      And a declared verify command is used as the role-default completion gate
      And worktree: true is used as the role-default Git isolation setting

    Scenario: Multi-line YAML tool lists are declared like inline lists
      Given an agent Markdown file whose tools frontmatter uses one dash item per line under "tools:"
      When the leader resolves that agent
      Then every dash-listed tool is declared and none is silently dropped

    Scenario: Agent descriptions are injected into prompt guidance
      Given agent definitions exist in bundled, user, or project scopes
      When a turn starts and before_agent_start runs
      Then each discovered agent's name, description, scope, tools, model, and verify are injected into prompt guidance

    Scenario: An unknown agent name fails the spawn
      When the leader spawns a teammate with an agent name that no scope defines
      Then the spawn is rejected and available agents are listed

  Rule: Teammates are named resident processes

    Scenario: Spawning creates one named resident teammate
      When the leader calls teammate_spawn with a unique name, an agent, and an optional kickoff prompt
      Then one resident child Pi process is started in RPC mode
      And the teammate joins the roster with status starting and then idle
      And the kickoff prompt is delivered as the teammate's first turn

    Scenario: Teammate names are unique among living teammates
      Given a teammate named security is on the roster
      When the leader spawns another teammate named security
      Then the spawn is rejected

    Scenario: The session-wide cap bounds resident teammates
      Given 8 teammates are alive in the session
      When the leader spawns one more teammate
      Then the spawn is rejected until a teammate is shut down

    Scenario: Idle teammates are suspended between turns
      Given a teammate finished its current turn
      Then its child process stays alive waiting on its control stream
      And it consumes no model tokens while idle
      And it keeps occupying one session worker slot until shutdown

    Scenario: Shutdown stops one teammate and frees its slot
      When the leader calls teammate_shutdown for a living teammate
      Then the child process receives SIGTERM with bounded SIGKILL escalation
      And the roster records the teammate as stopped
      And its session worker slot is released
      And worktree changes are captured and reported before teardown when the teammate owned a worktree

    Scenario: An unexpected teammate crash is reported to the leader
      Given a resident teammate's child process closes without a shutdown request
      When the close is observed
      Then the roster records the teammate as stopped with the exit diagnostic
      And the leader receives one crash diagnostic naming the teammate
      And any task the teammate held is released back to pending

    Scenario: Teammates do not survive session shutdown
      Given resident teammates are alive
      When the leader session shuts down
      Then every teammate child is terminated and shutdown confirms close where possible
      And the roster dies with the session
      And the task board persists for later inspection

    Scenario: Teammates run without turn or duration caps
      Given a teammate is woken by a delivery or a new prompt
      Then the wake-up sequence runs without any turn-count or wall-clock ceiling
      And no configuration may automatically terminate a working teammate
      And turn counts and silence durations exist only as telemetry and heartbeat signals for the leader's decisions

    Scenario: A silent working teammate raises one stall notice per episode
      Given a teammate is working and has produced no stream output for the stall-notice interval
      When the harness poll checks teammate liveness
      Then the roster records the last output time and a stall notice
      And the leader receives one actionable diagnostic naming the teammate
      And the notice wakes the idle leader without requiring model polling
      And the notice is the last automatic action: continuing, steering, shutting down, or respawning belongs to the leader alone

    Scenario: Activity re-arms the stall watchdog
      Given a teammate has already received a stall notice
      When any new RPC stream output arrives for that teammate
      Then the stall episode marker is cleared
      And a later silent episode can raise a fresh notice

  Rule: Messaging is peer-to-peer through local inboxes

    Scenario: Teammates exchange messages directly by name
      Given teammates security and backend are alive
      When security calls send_message with to="backend" and one message body
      Then the message is appended to backend's inbox file
      And the send succeeds only after the recipient inbox write succeeds
      And sending to an unknown teammate name fails

    Scenario: Delivered messages wake an idle teammate automatically
      Given teammate backend is idle
      When a peer message arrives in backend's inbox
      Then the harness poll wakes backend with the message content
      And the leader model performs no manual delivery step

    Scenario: Messages reach a working teammate without dropping
      Given teammate backend is working on a turn
      When a peer message arrives in backend's inbox
      Then the harness delivers the message into the running turn
      Or delivers it at the next wake-up if the control stream is momentarily unavailable
      And no message is silently discarded

    Scenario: Inbox delivery is at-least-once and deduplicated
      Given a peer message was delivered into a teammate turn
      When the same message id is observed again
      Then it is not delivered twice
      And no read receipt is stored or exchanged

    Scenario: Peer traffic never enters the leader's model context
      Given teammates exchange peer messages
      When the harness routes the traffic
      Then no peer message body is delivered to the leader as a follow-up or report
      And peer messages are inspectable in the /teammate console instead

    Scenario: Reports to the leader use the unified send_message primitive
      Given a teammate is working
      When it calls send_message with to="leader", one message body, and an optional status
      Then the message is appended to the teammate's outbox
      And the leader validates the teammate identity and spawn identity
      And the message lands in the single leader inbox
      And a status="completed" or status="failed" report ends the current assignment, with the teammate going idle when its current sequence ends
      And intermediate reports are recorded without interrupting the main session
      And status is rejected for peer-directed messages

    Scenario: A teammate whose last report lacks terminal status is asked to self-finalize first
      Given a teammate sent leader-bound messages but never status="completed" or "failed"
      When its current sequence ends and it goes idle
      Then the harness writes one finalize request into that teammate's inbox instead of alerting the leader
      And the request instructs send_message(to="leader") with status="completed" or status="failed"

    Scenario: A repeated unfinalized idle transition escalates to the leader
      Given a teammate already received one finalize request for this spawn incarnation
      When it goes idle again and its last leader-bound report still lacks terminal status
      Then the harness delivers one light leader reminder naming that teammate
      And neither request nor reminder repeats within the same spawn incarnation
      And neither fires when every report from that teammate was terminal

    Scenario: The leader addresses a living teammate by name through send_message
      When the leader calls send_message with a teammate name and one message body
      Then the message is written to that teammate's control stream or queued for its next wake-up
      And sending to "leader", an unknown teammate, or a stopped teammate fails

    Scenario: Stale spawn events cannot affect a newer teammate incarnation
      Given a teammate was restarted and holds a fresh spawn identity
      When an event arrives bearing the previous spawn identity
      Then the event is rejected

  Rule: The task board is shared coordination state

    Scenario: The leader creates tasks; teammates never do
      When the leader calls task_create with a subject and optional description, dependencies, and verify command
      Then the task joins the board as pending
      And workers have no task creation capability

    Scenario: Only resident teammates self-claim tasks
      Given a pending task with no unmet dependencies
      When an idle or working teammate calls task_claim
      Then exactly one claimer wins the atomic claim
      And the losing racer receives a claim failure instead of a shared claim
      And the winner's roster entry records the claimed task

    Scenario: Dependencies gate claimability
      Given a task depends on an incomplete task
      When teammates look at the board
      Then the dependent task is not claimable
      And when the last dependency completes, the task becomes claimable automatically
      And the shared task_list view includes the living roster on both leader and worker sides

    Scenario: Claimed tasks are released when their holder stops
      Given a teammate holds a claimed task
      When the teammate is shut down or crashes
      Then the task returns to pending
      And other teammates may claim it

    Scenario: Completion is submitted by the claimer and gated by verify
      Given a teammate holds a claimed task
      When it calls task_submit with status completed and a result
      Then the harness runs the effective verify command for the task
      And the effective verify is the task-level command, falling back to the agent-role default
      And a zero exit completes the task and frees the teammate
      And a non-zero exit keeps the task claimed and feeds stderr back to the teammate
      And without any verify command the submission itself completes the task

    Scenario: Failed submissions keep the task claimable by its holder
      Given a teammate submits a failed outcome for its task
      Then the task is released back to pending
      And the failure reason is recorded on the board

    Scenario: The board persists across restarts while the runtime does not
      Given a session recorded a task board
      When the session shuts down and a later session resumes the same board directory
      Then the board file remains on disk and readable
      And runtime state such as rosters, inboxes, and outboxes does not survive
      And claimed tasks held by dead teammates return to pending on reload
      And no automatic cleanup deletes persisted boards

    Scenario: Board state has one writer
      Given workers may race to claim or submit tasks
      When the harness applies board changes
      Then only the leader process writes the board file
      And workers express intent through exclusive-create marker files
      And a malformed intent is consumed and reported as a diagnostic without blocking others

  Rule: The harness wakes idle teammates, the leader model never polls

    Scenario: Idle teammates are poked only when there is something to do
      Given an idle teammate with no inbox messages and no claimable tasks
      Then the harness performs no wake-up and spends no tokens

    Scenario: Claimable-task notices respect a per-teammate pacing interval
      Given an idle teammate and an unclaimed pending task
      When the teammate declines to claim and stays idle
      Then the harness waits at least the pacing interval before the next notice

    Scenario: The leader guidance forbids sleep-based coordination
      Given the team leader is composing a reply while teammates work
      When before_agent_start builds the leader guidance
      Then the guidance instructs the leader to end its turn instead of sleeping or polling
      And wake-ups, deliveries, and verify outcomes arrive as automatic follow-ups

    Scenario: The leader guidance teaches recovery over punishment
      Given the leader receives a stall notice for a wedged teammate
      When before_agent_start builds the leader guidance
      Then it explains deciding to keep waiting, steer again, shut down, or respawn a successor
      And a respawn composes context from the original kickoff, mailbox reports, board claims, and the console detail transcript
      And the harness never reclaims, restarts, or replaces a teammate on its own

  Rule: Leader tool surface is exact

    Scenario: Spawning renders one started line per teammate
      Given the leader spawns a teammate with a kickoff prompt
      When the spawn tool call renders in the transcript
      Then it shows one started line identifying the teammate and kickoff task
      And the line follows the `[agent] started · @name · task-name` shape
      And the started line fits the available TUI width with a trailing ellipsis when needed
      And the full result text stays available behind the standard tool rendering

    Scenario: The teammate_spawn started row fits narrow transcript widths
      Given the leader spawns a teammate with a long name and kickoff prompt
      When the started row renders in a narrow transcript
      Then the row stays on one line and does not exceed the available width

    Scenario: The leader coordinates through spawn, shutdown, steer, and the board
      When the leader inspects available tools
      Then teammate_spawn, teammate_shutdown, send_message, task_create, and task_list are registered
      And teammate_message, teammate_run, teammate_fanout, teammate_cancel, and teammate_retry are not registered
      And no teammate_status, teammate_wait, or polling tool is registered

    Scenario: Invalid operations surface as Pi failures
      Given a leader or worker invokes a capability outside its valid state or authorization
      When the operation cannot be completed
      Then the tool throws an error for Pi to record as a failed tool call

    Scenario: Workers cannot access leader tools
      Given a teammate is working
      When it tries to spawn or shutdown teammates or create tasks
      Then no such capability is available

  Rule: Prompt guidance reflects the team model

    Scenario: Leader guidance teaches the team workflow statically
      Given agent definitions exist
      When before_agent_start builds the leader guidance
      Then it explains spawning named teammates, creating board tasks, and steering by name
      And it embeds no live roster or board state
      And the guidance is byte-identical across turns while agents and cwd are unchanged

    Scenario: Worker guidance teaches the resident protocol
      Given a teammate process starts
      When before_agent_start runs inside the teammate
      Then the system prompt gains the resident protocol
      And the protocol covers reporting, peer messaging, claiming, submitting, and inbox wake-ups
      And it states that peer messages may arrive mid-turn from other Claude-style teammates

  Rule: Worktree isolation is an agent-role option

    Scenario: A worktree role owns a git worktree
      Given an agent definition declares worktree: true in a git repository
      When the leader spawns a teammate with that agent
      Then the teammate works in its own worktree on its own branch
      And shutdown captures the diff against the base commit for integration review

    Scenario: Worktree-role setup failure fails the spawn cleanly
      Given an agent definition declares worktree: true and worktree creation fails
      When the leader spawns a teammate with that agent
      Then the spawn fails before any child process starts
      And the error names the worktree problem

  Rule: Console and widget visualize the team without intercepting input

    Scenario: The widget shows only working teammates
      Given teammates are alive
      When the passive widget renders
      Then each working or starting teammate renders one spinner row with live activity
      And idle and stopped teammates never appear above the input box
      And the widget stays hidden when nobody is working
      And it does not intercept global terminal input

    Scenario: The agent-teams menu opens the team console
      When the user opens /agent-teams and chooses `console`
      Then the roster page and board page open in the full-screen team console
      And the legacy /teammate command is not registered

    Scenario: The agent-teams menu creates a project agent from history
      Given the project agents directory exists
      When the user opens /agent-teams and chooses `project` (create project agent)
      And provides a valid agent name
      Then a git-managed `.pi/agents/<name>.md` definition is created
      And its prompt is derived from the current session branch history
      And an existing definition is never overwritten

    Scenario: The agent-teams menu creates a local agent from history
      Given the project agents directory exists
      When the user opens /agent-teams and chooses `local` (create project-local agent)
      And provides a valid agent name
      Then a non-git-managed `.pi/agents/<name>.local.md` definition is created
      And its prompt is derived from the current session branch history
      And project-local discovery deduplicates any same-name project definition

    Scenario: Agent creation rejects invalid or duplicate names
      When the user chooses project or local agent creation with an invalid or existing name
      Then creation fails with a validation error
      And no existing agent definition is modified

    Scenario: The console has a roster page and a board page
      When the user opens /agent-teams
      Then the roster page lists every roster entry with status, agent, and live activity, including idle and stopped teammates
      And the board page lists tasks with status, claimant, and subject
      And enter opens a detail view for either selection
      And x shuts down the selected living teammate
      And tab switches between roster and board pages
      And detail views expose reports to the leader and peer mail transcripts
      And a teammate's current board task appears in its detail view
      And detail scrolling preserves wrapped lines with keyboard and mouse-wheel navigation

    Scenario: Detail views expose transcripts
      Given a teammate exchanged peer messages and reports
      When its detail view opens
      Then reports to the leader and peer traffic are listed with timestamps

  Rule: Shared worker runtime owns process identity and configured user paths

    Scenario: User-scoped agent state honors the configured Pi agent directory
      Given PI_CODING_AGENT_DIR points to a custom agent directory
      When the leader discovers user agents or writes team state
      Then it reads and writes below that configured directory
      And it does not reconstruct ~/.pi/agent directly

    Scenario: Teammate children run with only the agent-teams extension
      Given a teammate is spawned
      When the child Pi process starts
      Then unrelated session extensions are disabled
      And the agent-teams worker extension is loaded explicitly
      So extension startup failures cannot masquerade as teammate work

  Rule: Acceptance workflow — three-way review with cross-challenge

    Scenario: Three independent reviewers converge through peer messaging
      Given the leader spawns security, performance, and tests teammates from reviewer-style agents
      And the leader creates one review task per lens on the board
      When each reviewer claims its task and reviews independently
      And reviewers exchange top findings and challenges through send_message
      And each reviewer submits its task with a verify command that must pass
      Then completions are gated by the verify commands rather than self-report
      And the leader synthesizes the final review from the three completed tasks
      And peer challenges never passed through the leader's context
