Feature: Agent Teams collaborative organization contract
  Agent Teams gives Pi a Claude-Code-style team layer: named resident
  teammates, a shared local task board with self-claim, and peer-to-peer
  messaging between teammates. Agents are declarative Markdown files
  (user, project, and project-local scopes); there are no built-in roles. The team leader spawns named
  teammates as long-lived child Pi processes in RPC mode; idle teammates
  are woken by harness polling (inbox delivery and claimable-task
  notices), never by leader-model busywork. Task completion is gated by
  deterministic verify commands; peer traffic never enters the leader's
  model context.

  Background:
    Given the pi-agent-teams-fradser extension is loaded

  Rule: Agents are declarative Markdown files

    Scenario: Discover agents from user, project, and project-local scopes
      When the leader queries agent definitions
      Then user agents under the Pi global agents directory are available
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
      Given agent definitions exist in user, project, or project-local scopes
      When a turn starts and before_agent_start runs
      Then each discovered agent's name, description, scope, tools, model, and verify are injected into prompt guidance

    Scenario: Generated roles stay in memory by default
      Given no definition exists for the requested agent name
      When the leader derives a role from the task and shipped abstract role reference without a persistence request
      Then it registers the definition in the current session's memory
      And the role is discovered with session scope and no filesystem source
      And no agent definition file is written
      And the role disappears when the session starts again

    Scenario: Generated roles can be persisted only after an explicit request
      Given no definition exists for the requested agent name
      When the user explicitly asks to keep the role for future sessions
      Then the leader sets definition.persist=true and writes a project or project-local definition before spawning
      And the persisted role is discovered from that filesystem scope

    Scenario: An unknown agent name fails the spawn
      When the leader spawns a teammate with an agent name that no scope defines
      Then the spawn is rejected and available agents are listed

    Scenario: Spawning an unknown agent names the recovery path
      Given an available-agents list whose definition files changed mid-session
      When the leader spawns an agent name that no scope defines anymore
      Then the failure reports every checked scope including the project agents directory and the configured user agents directory
      And it explains that the guidance list may be stale
      And it lists the agent names currently discoverable in any scope
      And it points to creating the role on demand from the shipped role reference

    Scenario: Persistent definitions outrank generated session roles
      Given a generated session role and a definition file share the same teammate name
      When the leader resolves that name
      Then the filesystem definition wins at its declared scope
      And generated session roles only fill names that no file defines

    Scenario: A new inline definition replaces a stale generated role of the same name
      Given a generated session role exists for an agent name from an earlier spawn this session
      When the leader spawns that name again while supplying an explicit inline definition
      Then the new definition's tools, model, verify, worktree, and prompt take effect
      And the role remains session-scoped and no definition file is written

    Scenario: Definition files outrank an inline definition of the same name
      Given a definition file exists for the requested agent name
      When the leader spawns it while also supplying an inline definition of the same name
      Then the file-based definition is used unchanged
      And no definition file is modified

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

    Scenario: Shutdown after a finish announcement adds no second event line
      Given a teammate whose terminal report already announced its finish entry
      When the leader shuts that teammate down
      Then no shutdown event line renders for that incarnation
      And the finish entry stays the single end-of-life announcement

    Scenario: Shutdown without a finish announcement keeps its event line
      Given a living teammate that announced no terminal report
      When the leader shuts that teammate down
      Then the shutdown event line renders with its expandable diagnostics

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
      And peer messages are inspectable in the /agent-teams console instead

    Scenario: Reports to the leader use the unified send_message primitive
      Given a teammate is working
      When it calls send_message with to="leader", one message body, and an optional status
      Then the message is appended to the teammate's outbox
      And the leader validates the teammate identity and spawn identity
      And the message lands in the single leader inbox
      And a status="completed" or status="failed" report ends the current assignment, with the teammate going idle when its current sequence ends
      And intermediate reports are recorded without interrupting the main session
      And status is rejected for peer-directed messages

    Scenario: Completion is announced once per spawn incarnation
      Given a teammate delivered several leader-bound reports carrying terminal status within one spawn
      When the report batches render in the transcript
      Then exactly one "Teammate finished" entry is appended for that teammate and spawn identity
      And repeated terminal reports from the same spawn stay ordinary report rows without extra finished entries
      And respawning a teammate with the same name announces its completion again

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

    Scenario: Task ids are readable slugs of their subjects
      Given the leader creates a task titled "Polish login flow"
      When the board assigns its id
      Then the id is a sanitized slug of the title such as "polish-login-flow"
      And a second task with the same title gets a distinct numbered id within the length cap
      And a resumed board keeps its old ids while new tasks still get unique slugs

    Scenario: Task lookups never alias inherited object properties
      Given the leader creates a task whose slug id is a prototype name such as "constructor"
      When the board stores and resolves that task
      Then the task is its own entry and dependency checks see only real board entries

    Scenario: Repeated verify failures escalate instead of looping
      Given a teammate holds a claimed task whose gate cannot pass
      When submissions fail verification a second consecutive time
      Then the task remains claimed by the holder without another resubmit invitation
      And the leader receives one escalation naming the task and the verify output
      And further failed submissions stay quiet toward the leader until a new holding begins

    Scenario: A stopped holder leaves no verify-failure residue
      Given a teammate accumulated verify failures on its claimed tasks
      When the teammate stops and its claimed tasks are released
      Then no verify-failure record remains keyed to the released holder incarnation

    Scenario: A verify result belongs to exactly one submission
      Given a claimed task whose verify command is running
      When the holder releases the task and re-claims it before the verify resolves
      Then the stale verify result cannot complete the new holding
      And a fresh submission after the re-claim runs its own gate to completion

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

    Scenario: Declined claimable work does not wake an idle teammate twice
      Given an idle teammate and an unclaimed pending task
      When the teammate is woken by the notice, declines to claim, and goes idle again
      Then the same task never wakes that teammate again
      And the teammate is woken only by new mail or newly claimable work

    Scenario: Recording new notices retains ids of tasks still claimable
      Given a long board whose noticed history exceeds the retention window
      When the teammate is notified about further work
      Then stale non-claimable ids are pruned first
      And ids of tasks still claimable survive and never re-wake the teammate

    Scenario: Released tasks are noticeable again
      Given a task whose id an idle teammate was already notified about
      When the task is released back to pending
      Then the task may wake teammates once more

    Scenario: Claimable-task notices respect a per-teammate pacing interval
      Given an idle teammate and newly claimable work
      When notice delivery is attempted in quick succession
      Then the harness waits at least the pacing interval between notices

    Scenario: Notice pacing defaults to minutes and is configurable
      Given no pacing configuration is set
      Then claimable-task notices wait at least five minutes between deliveries by default
      And PI_TEAMMATE_NOTICE_PACE_MS overrides the default in milliseconds

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
      And a failed spawn keys off the render context isError flag and renders one plain error line

    Scenario: The teammate_spawn started row fits narrow transcript widths
      Given the leader spawns a teammate with a long name and kickoff prompt
      When the started row renders in a narrow transcript
      Then the row stays on one line and does not exceed the available width

    Scenario: Shutting down renders one collapsible agent event line
      Given the leader shuts down a teammate
      When the shutdown tool call renders in the transcript
      Then it shows one event line following the `[agent] event · @name shut down` shape
      And the collapsed line appends the shared dim expand hint from pi-kit
      And expanding the line reveals the shutdown detail lines such as exit code, released tasks, and usage
      And the event line is never labeled as a monitor event
      And a failed shutdown keys off the render context isError flag and renders one plain error line without an event row

    Scenario: Steering renders one delivery line per message
      Given the leader sends a message to a living teammate
      When the send_message tool call renders in the transcript
      Then the call slot renders no content of its own
      And the result renders one delivery line following the `[message] to @name` shape
      And the line appends the delivery outcome such as delivered or queued as a dim suffix
      And the line flags a stalled recipient with its silence duration instead of a duplicate sentence
      And the full result text stays available to the model without a second transcript row
      And a failed delivery keys off the render context isError flag and renders one plain error line without an outcome suffix

    Scenario: Creating a board task renders one created line
      Given the leader creates a board task
      When the task_create tool call renders in the transcript
      Then the call slot renders no content of its own
      And the result renders one `[board] created · <subject>` line truncated to the available width
      And a failed creation keys off the render context isError flag and renders one plain error line without a created row

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

    Scenario: The agent-teams command opens the console directly
      When the user runs /agent-teams in a TUI session
      Then the full-screen team console opens without any intermediate menu
      And the legacy /teammate command is not registered

    Scenario: Non-TUI sessions receive a text summary instead of the console
      When the user runs /agent-teams outside TUI mode
      Then the team status summary is delivered as a notification
      And no interactive console opens

    Scenario: The console roster separates session teammates from persistent agent roles
      Given agent definitions exist in user, project, or project-local scopes
      When the console renders its roster page
      Then session teammates appear under a teammates section with runtime status and live activity
      And deduplicated persistent definitions appear under an agent roles section with scope provenance, definition source, and live instance counts

    Scenario: The console has a roster page and a board page
      When the user runs /agent-teams
      Then the roster page lists every roster entry with status, agent, and live activity, including idle and stopped teammates
      And the roster page lists persistent agent roles after the session teammates
      And each role row carries scope provenance, the definition source, and live instance counts
      And the board page lists tasks with status, claimant, and subject
      And enter opens a detail view for either selection
      And x asks for confirmation before shutting down the selected living teammate
      And tab switches between roster and board pages
      And detail views expose reports to the leader and peer mail transcripts
      And a teammate's current board task appears in its detail view
      And detail scrolling preserves wrapped lines with keyboard and mouse-wheel navigation

    Scenario: A role row opens a read-only definition preview
      Given an agent definition exists in any scope
      When the user opens its role row in the console
      Then the detail view shows the definition source, frontmatter fields, and role prompt
      And the preview offers no edit or write action

    Scenario: Teammates are shut down from the console with confirmation
      When the user requests shutdown for a living teammate in the console and confirms
      Then that teammate shuts down and its claimed task returns to the board
      But cancelling the confirmation leaves the teammate untouched

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
