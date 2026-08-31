Feature: Agent Teams collaborative organization contract
  Agent Teams gives Pi a Claude-Code-style team layer: named resident
  teammates, a shared local task board with self-claim, and peer-to-peer
  messaging between teammates. Agents are declarative Markdown files
  (user, project, and project-local scopes); there are no built-in roles. The team leader spawns named
  teammates as long-lived child Pi processes in RPC mode; idle teammates
  are woken by harness polling (inbox delivery and claimable-task
  notices), never by leader-model busywork. Task completion is gated by
  verify prompts that a fresh one-shot reviewer answers with a VERDICT;
  peer traffic never enters the leader's model context.

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
      And a declared verify prompt is used as the role-default completion gate
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

    Scenario: Direct kickoff tasks execute immediately without querying the task board
      Given a teammate is spawned with an assigned kickoff prompt
      When the kickoff prompt is constructed
      Then it instructs the teammate to execute the assigned task directly without checking task_list
      And worker guidance instructs teammates to use task_list only when idle or notified of unclaimed work

    Scenario: Direct-assignment completion does not require a board snapshot
      Given a teammate has a direct assignment or review kickoff
      When the leader waits for its result
      Then the teammate's terminal report is the sole completion signal
      And the leader does not call task_list merely to see whether the teammate is still working
      And task_list remains available when task-board state is needed for a concrete coordination decision

    Scenario: A terminal direct assignment cannot drift into board work
      Given a teammate completed a direct assignment with a terminal leader report
      And pending board work exists
      When the teammate becomes idle
      Then the harness does not send a board notice to that teammate
      And task_claim rejects board work until the leader explicitly opens a new assignment

    Scenario: Reopen cannot replace active direct work
      Given a teammate owns an active direct assignment for resource "firmware/sub-node"
      When the leader attempts reopen=true with another direct assignment
      Then the harness rejects the reopen until the original assignment is terminal or released
      And the original resource reservation remains active

    Scenario: Generic wake-up cannot reopen a closed direct assignment
      Given a teammate terminally completed a direct assignment for resource "firmware/sub-node"
      When peer or harness mail wakes it before the leader sends another assignment
      Then its terminal direct assignment remains closed
      And an ordinary leader steer is rejected until reopen=true

    Scenario: A board claim remains open until task_submit completes it
      Given a teammate claimed a board task
      When it sends a terminal leader report without task_submit
      Then the task remains claimed by that teammate
      And the harness asks the teammate to submit the board outcome
      And the teammate cannot claim another board task

    Scenario: Resource-scoped assignments cannot overlap
      Given one living teammate owns an active assignment for resource "firmware/sub-node"
      When another teammate claims a task scoped to "firmware/sub-node/app"
      Then the harness rejects the claim with the conflicting assignment
      And unrelated resources remain claimable

    Scenario: A successor receives structured handoff context
      Given a stalled teammate has an active assignment, board claim, and leader reports
      When the leader spawns a successor with handoffFrom set to that teammate
      Then the successor kickoff includes the prior assignment, claim, and recent reports
      And the successor does not automatically inherit the prior claim
      And handoffFrom is rejected until the predecessor is stopped

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

    Scenario: Shutdown while the finish report is queued adds no event line either
      Given a teammate whose terminal report reached the leader pipeline but has not been dispatched yet
      When the leader shuts that teammate down
      Then no shutdown event line renders for that incarnation
      And the queued finish entry remains the single end-of-life announcement

    Scenario: Shutdown without a finish announcement keeps its event line
      Given a living teammate that announced no terminal report
      When the leader shuts that teammate down
      Then the shutdown event line renders with its expandable diagnostics
      And the requested shutdown does not create a leader follow-up message

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
      And the transcript renders the health diagnostic as one `[agent] @name stalled · silent <duration>` row
      And message routing rows never repeat the teammate health state
      And the notice wakes the idle leader without requiring model polling
      And the notice is the last automatic action: continuing, steering, shutting down, or respawning belongs to the leader alone

    Scenario: Activity re-arms the stall watchdog
      Given a teammate has already received a stall notice
      When any new RPC stream output arrives for that teammate
      Then the stall episode marker is cleared
      And a later silent episode can raise a fresh notice

    Scenario: A provider hang is flagged before the default stall window
      Given a working teammate has received no recognized stream activity and runs no tool
      When its silence passes the silent-stall interval while staying under the default stall-notice interval
      Then the leader receives one stall notice reporting zero model output
      And the notice names shutdown plus respawn as the effective remedy instead of steering

    Scenario: Recognized stream activity counts as output regardless of usage totals
      Given a working teammate whose stream delivered text, thinking, or tool events without usage totals
      When its silence grows past the silent-stall interval
      Then the general stall window governs instead of the provider-hang tier
      And an empty message_end artifact alone never counts as model output

    Scenario: Stall notices carry lifetime usage diagnostics
      Given a silent working teammate with recorded lifetime token usage
      When the harness raises a stall notice for that teammate
      Then the body reports the silence duration, spawn age, and lifetime usage totals

  Rule: Messaging is peer-to-peer through local inboxes

    Scenario: Teammates exchange messages directly by name
      Given teammates security and backend are alive
      When security calls send_message with to="backend" and one message body
      Then the message is appended to backend's inbox file
      And the send succeeds only after the recipient inbox write succeeds
      And the synchronous routing outcome is queued because harness delivery into a turn is still pending
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

    Scenario: Peer-message delivery is auditable without claiming it was read
      Given teammate analyst sends a peer message to teammate critic
      When the harness routes the message into critic's turn or pending delivery queue
      Then the peer transcript records the message as harness-delivered
      And the transcript does not claim that critic read, accepted, or answered it

    Scenario: A facilitated discussion keeps participant reports out of the leader turn
      Given teammates are conducting a peer discussion with a named moderator
      When a non-moderator needs to challenge or answer another participant
      Then it addresses that participant through send_message instead of reporting the exchange to the leader
      And it sends the leader only one terminal contribution after the moderator requests closure
      And the moderator's terminal report cites the peer discussion before synthesis

    Scenario: Late reports from a stopped teammate are archived instead of waking the leader
      Given a teammate has reports pending in the automatic follow-up queue
      When that teammate is shut down before those reports dispatch
      Then its pending reports remain inspectable as archived diagnostics
      And they do not start another leader turn

    Scenario: A report written while shutdown is closing is archived too
      Given a teammate writes a leader report before its child process closes for a requested shutdown
      When the harness drains that final outbox during close handling
      Then the report is archived as a shutdown diagnostic
      And it does not start another leader turn

    Scenario: Reports to the leader use the unified send_message primitive
      Given a teammate is working
      When it calls send_message with to="leader", one message body, and an optional status
      Then the message is appended to the teammate's outbox
      And the leader validates the teammate identity and spawn identity
      And the message lands in the single leader inbox
      And a status="completed" or status="failed" report ends the current assignment, with the teammate going idle when its current sequence ends
      And every leader-bound report, intermediate or terminal, is queued for the leader as its own follow-up turn
      And status is rejected for peer-directed messages

    Scenario: A report enters Pi's native follow-up queue while the leader is active
      Given the leader is processing an active run
      When a teammate sends a leader-bound report
      Then Agent Teams dispatches that report without waiting for agent_settled
      And Pi retains the report as a follow-up until the current run can end
      And Agent Teams does not dispatch a later report until the dispatched report settles

    Scenario: Teammate messages are rationed by value instead of throttled
      Given the worker messaging protocol
      Then it states that every leader-bound message starts a full leader turn
      And it forbids bare status pings that carry no new information
      And it keeps immediate reporting for blockers, plan-changing facts, and final deliverables
      And it combines the final outcome, evidence, verification, and remaining risks in one substantive terminal report when relevant
      And it puts status="completed" or status="failed" on that final substantive report
      And it does not send a separate completion-only message after the final report
      And it avoids repeating the same findings across reports unless new information changes the conclusion
      And it keeps terminal status mandatory when the assignment ends

    Scenario: Bounded reviewer assignments end with one substantive report
      Given a reviewer is completing a bounded assignment for the leader
      When it has findings, a recommendation, and verification evidence
      Then one concise terminal report bundles those findings, the recommendation, verification, and remaining risks
      And earlier leader reports are limited to genuinely new blockers, plan-changing facts, or evidence that changes the conclusion
      And the reviewer does not send a separate status-only assignment-complete message
      And after the terminal report, leader reporting resumes only for a new assignment or decision-useful fact
      And the terminal report carries status="completed" or status="failed"

    Scenario: Completion is announced once per spawn incarnation
      Given a teammate delivered several leader-bound reports carrying terminal status within one spawn
      When the reports arrive as separate follow-up messages
      Then exactly one "Teammate finished" entry is appended for that teammate and spawn identity
      And repeated terminal reports from the same spawn stay ordinary report rows without extra finished entries
      And respawning a teammate with the same name announces its completion again

    Scenario: A terminal report closes reporting until a new wake-up or explicit new assignment
      # A terminal report closes reporting until a new wake-up only when the wake-up is an explicit new assignment.
      Given a teammate sends a leader-bound report with status="completed" or status="failed"
      When later reports from that same spawn arrive
      Then those reports are suppressed instead of starting more leader turns
      And distinct decision-useful intermediate reports sent before the terminal report remain deliverable
      And the harness does not emit a duplicate completion-only follow-up
      When the leader sends an ordinary steer to that teammate
      Then the steer is rejected without reopening its report sequence
      When the leader explicitly marks a new assignment with reopen=true
      Then the teammate receives the new assignment and its report sequence reopens
      And identical intermediate reports before a terminal status remain deliverable

    Scenario: The leader reads a recorded terminal report without forcing a resend
      Given a teammate's terminal report is recorded and its delivery to the leader is automatic
      When the leader addresses that teammate with an ordinary send_message
      Then no new message is delivered and the result returns the recorded terminal report body
      And it warns that asking the teammate to resend produces a duplicate leader turn
      When the leader reopens that teammate for a distinct assignment
      Then the result again includes the recorded terminal report and the duplicate warning
      And the leader never needs to ask a teammate to repeat an already-sent report

    Scenario: Delivered report details retain terminal evidence
      Given a teammate sends a leader-bound report
      When the parent queues it as a leader follow-up
      Then the follow-up details retain the outbox event id and status
      And the status distinguishes an actual terminal report from terminal-looking prose

    Scenario: A terminal worker report ends its current worker turn
      Given a teammate sends a leader-bound report with status="completed" or status="failed"
      When its send_message tool result returns
      Then the result terminates the current worker turn
      And the harness marks the teammate idle without waiting for another stream event
      And a status-less or in-progress report does not terminate the turn

    Scenario: Suppressed report events remain replay-safe
      Given a terminal report has closed a teammate's current report sequence
      When a later outbox event is suppressed
      Then its exact event id is still consumed for replay protection
      And replaying that event does not deliver it after the sequence reopens

    Scenario: Leader-relevant harness events ride the same delivery channel
      When a worktree teammate shuts down with captured changes
      Or a verify gate fails repeatedly enough to need manual attention
      Or a resident teammate stops unexpectedly
      Then the event is queued for the leader through the same follow-up channel as worker reports
      And the event uses a harness-event envelope instead of an agent-message envelope
      And actionable worktree capture or cleanup failures wake the leader through that envelope
      And purely operational logs stay inspectable in the /agent-teams console without starting leader turns

    Scenario: Malformed report timestamps are rejected safely
      Given a teammate outbox contains a report with a non-finite timestamp
      When the harness drains the outbox
      Then it treats the record as malformed instead of crashing report delivery
      And it ignores the non-finite timestamp when formatting any retained report
      And later valid reports remain deliverable

    Scenario: Requested shutdown stays a tool lifecycle event
      Given a living teammate is shut down by the leader
      When the shutdown completes
      Then the transcript shows the requested shutdown through the tool lifecycle row
      And no asynchronous harness follow-up is sent for the clean shutdown

    Scenario: The leader waits for a terminal report before intentional shutdown
      Given a teammate is still working on an assignment
      When the leader considers shutting it down after the work appears complete
      Then the leader guidance says to wait for status="completed" or status="failed" when possible
      And intentional shutdown is not treated as proof that the assignment completed

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

    Scenario: A peer-only kickoff does not synthesize a leader report
      Given a teammate spawned with a kickoff that only communicates with peers
      When its current turn ends and it goes idle without sending a leader-bound report
      Then the harness does not synthesize a kickoff-without-report event
      And the leader remains quiet until the teammate actively sends a report to="leader"
      And a prompt-less board-check spawn idling also remains quiet

    Scenario: The leader addresses a living teammate by name through send_message
      When the leader calls send_message with a teammate name and one message body
      Then the routing outcome is steered only when the message is written to that teammate's active control stream
      Or the routing outcome is queued when harness delivery must wait for the next wake-up
      And neither outcome claims the teammate read, understood, or processed the message
      And sending to "leader", an unknown teammate, or a stopped teammate fails
      And a stray status field on a leader-sent message does not block delivery; it is ignored with a one-line note

    Scenario: Stale spawn events cannot affect a newer teammate incarnation
      Given a teammate was restarted and holds a fresh spawn identity
      When an event arrives bearing the previous spawn identity
      Then the event is rejected

    Scenario: Stale submission reducers cannot complete a same-named replacement
      Given a task was re-claimed by a teammate with a fresh spawn identity
      When an old spawn submits completion for the same teammate name
      Then the reducer rejects it
      And the fresh holder keeps the claim

  Rule: The task board is shared coordination state

    Scenario: The leader creates tasks; teammates never do
      When the leader calls task_create with a subject and optional description, dependencies, and a verify prompt
      Then the task joins the board as pending
      And workers have no task creation capability

    Scenario: Creating a task reports the next execution action
      Given the leader has no living teammates
      When the leader creates a board task
      Then the task remains pending
      And the result tells the leader to spawn a teammate because task_create never spawns one automatically
      And the result says the task belongs to the current session board

    Scenario: Creating a task wakes an existing idle teammate immediately
      Given an idle teammate is already running in the current session
      When the leader creates a claimable board task
      Then the harness attempts the board notice immediately instead of waiting for the next poll tick
      And the task-create result reports the notification outcome

    Scenario: Only resident teammates self-claim tasks
      Given a pending task with no unmet dependencies
      When an idle or working teammate calls task_claim
      Then exactly one claimer wins the atomic claim
      And the losing racer receives a claim failure instead of a shared claim
      And the winner's roster entry records the claimed task

    Scenario: Claim intent is not work authorization
      Given a worker exclusively creates a claim marker
      When the leader reducer has not yet accepted it
      Then task_claim reports a queued claim intent rather than ownership
      And the worker is instructed not to start work
      When the reducer accepts the claim
      Then the harness sends Claim accepted and authorizes work

    Scenario: Dependencies gate claimability
      Given a task depends on an incomplete task
      When teammates look at the board
      Then the dependent task is not claimable
      And when the last dependency completes, the task becomes claimable automatically
      And the shared task_list view includes the living roster on both leader and worker sides

    Scenario: Task list groups board state around executable tasks
      Given the current session board has pending, claimed, and completed tasks
      When the leader or a worker calls task_list
      Then the result names the current session task board once
      And it reports one task summary with counts and claimable work
      And each task line identifies status, subject, claimant, and dependency state without repeating board prose
      And the roster is a separate compact section after the task section

    Scenario: Task creation reports one actionable board handoff
      Given the leader creates a task on the current session board
      When task_create returns
      Then the result groups the task identity, status, claimability, routing outcome, and next action
      And it does not repeat the full roster or duplicate the task description

    Scenario: Board result text uses stable semantic sections
      Given task_create or task_list returns board information
      When the leader reads the result
      Then the board context appears under `BOARD`
      And task state appears under `TASKS` or `CREATED`, `CLAIMED`, or `SUBMITTED`
      And next actions appear under `NEXT`
      And roster information appears only under `ROSTER`

    Scenario: Task claim reports ownership and the next task action
      Given a worker claims a pending task
      When task_claim returns
      Then the result names the task subject and new claimant
      And it tells the worker to do the work and submit the task outcome

    Scenario: Task submission reports verification routing
      Given a worker submits a claimed task outcome
      When task_submit returns
      Then the result names the task and submitted status
      And it says whether a verify review is queued or no review is configured
      And it does not claim that the task is completed before the harness applies the submission

    Scenario: Claimed tasks are released when their holder stops
      Given a teammate holds a claimed task
      When the teammate is shut down or crashes
      Then the task returns to pending
      And other teammates may claim it

    Scenario: Completion is submitted by the claimer and gated by verify
      Given a teammate holds a claimed task
      When it calls task_submit with status completed and a result
      Then the harness runs the effective verify prompt in a fresh one-shot reviewer
      And the effective verify is the task-level prompt, falling back to the agent-role default
      And a VERDICT: PASS completes the task and frees the teammate
      And a VERDICT: FAIL keeps the task claimed and feeds the reviewer's findings back to the teammate
      And without any verify prompt the submission itself completes the task

    Scenario: A missing verifier verdict is inconclusive, not a failed task
      Given a completion review returns findings without a VERDICT line
      When the harness asks once for a machine-readable verdict and it is still absent
      Then the task remains claimed without incrementing verify-failure count
      And the leader receives an inconclusive-verification decision request
      And after an explicit leader steer to the board holder the task may accept a new completed outcome with a fresh clarification allowance
      And the harness rejects completed submissions while that inconclusive task is parked
      And a rejected reopen request does not unpark the task
      And an ordinary leader steer can unpark an active board holder even after its terminal leader report

    Scenario: A task cannot replace an in-flight verification submission
      Given a claimed task has a completion review or verdict clarification running
      When its holder submits another completed outcome
      Then the harness rejects it without replacing the active submission identity
      And the holder waits for the current verification to settle

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
      And the leader receives one escalation naming the task and the reviewer's findings
      And the harness rejects completed resubmissions until an explicit leader steer to that board holder
      And further failed submissions stay quiet toward the leader until a new holding begins

    Scenario: A replacement task supersedes obsolete board work
      Given a pending or claimed board task was replaced by a newer leader plan
      When the leader creates a task that supersedes it
      Then the obsolete task is marked superseded and cannot be claimed or completed
      And a previous live holder keeps its resource reservation until it acknowledges cancellation or stops
      And the harness tells that holder to stop writing and acknowledge cancellation
      And board notices never advertise superseded work

    Scenario: A persisted superseded task releases its dead holder on resume
      Given a superseded task was held when its session stopped
      When a later session loads the board without that worker
      Then the task remains superseded for audit
      And its stale claimedBy field is cleared
      And it reserves no resource in the new session

    Scenario: Superseding a prerequisite migrates downstream dependencies
      Given pending task B depends on pending task A
      When the leader creates replacement R that supersedes A
      Then B depends on R instead of A
      And B becomes claimable after R completes
      And a replacement cannot both depend on and supersede the same task
      And a replacement that depends on B is rejected before creating the A-B-R cycle
      And superseding an already-superseded A targets its latest replacement before validation
      And superseding a completed task is rejected without retargeting downstream work
      And superseding A is rejected when A's latest replacement is completed

    Scenario: New work follows an existing supersession chain
      Given task A was superseded by replacement R
      When the leader creates task B with dependsOn A
      Then B depends on R instead of A
      And B is claimable after R completes
      But a persisted superseded task without supersededBy is rejected as an invalid dependency

    Scenario: A stopped holder leaves no verify-failure residue
      Given a teammate accumulated verify failures on its claimed tasks
      When the teammate stops and its claimed tasks are released
      Then no verify-failure record remains keyed to the released holder incarnation
      And inconclusive and explicit-failure parks are cleared on both close paths

    Scenario: A verify result belongs to exactly one submission
      Given a claimed task whose verify review is running
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

    Scenario: Board persistence is scoped to a board directory
      Given two Pi sessions use different session files in the same project
      When the first session creates a task
      Then the second session does not import that task automatically
      And resuming requires the same board directory

    Scenario: Board state has one writer
      Given workers may race to claim or submit tasks
      When the harness applies board changes
      Then only the leader process writes the board file
      And workers express intent through exclusive-create marker files
      And a malformed intent is consumed and reported as a diagnostic without blocking others
      And an intent requires non-empty taskId, worker, spawnId, and finite timestamp

    Scenario: Submission markers require a completed or failed status
      Given a claimed task with no completion gate
      When a malformed submission marker carries another status value
      Then the harness consumes it as a diagnostic
      And the task remains claimed and incomplete
      And every exported submission reducer rejects the same malformed status

  Rule: Worker board controls are progressively disclosed

    Scenario: Worker board controls follow board-notice and claim transitions
      Given a spawned teammate starts without a board assignment
      Then only send_message is active from the teammate capability set
      When the harness delivers a BOARD NOTICE for eligible unassigned work
      Then task_list and task_claim become active
      And task_submit remains inactive until the harness accepts a claim
      When the harness records an accepted board assignment for that teammate
      Then task_list and task_claim are removed and task_submit becomes active
      And an unrelated prompt that says Claim accepted does not activate task_submit
      When the teammate submits its accepted task outcome
      Then task_list, task_claim, and task_submit are removed
      When the teammate session shuts down before submission
      Then task_list, task_claim, and task_submit are removed
      When a new worker session starts after a terminal leader report before submission
      Then task_list and task_claim remain inactive while task_submit stays active for the claimed task
      And unrelated active tools remain active throughout

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

    Scenario: The leader guidance requires explicit worker tooling
      Given the leader derives an inline role for file-inspecting work
      When before_agent_start builds the leader guidance
      Then it warns that a definition without tools grants only the capability set
      And it instructs respawning with read and bash when a teammate reports missing capabilities instead of steering it

  Rule: Leader controls are progressively disclosed

    Scenario: Leader controls follow living-team and board state
      Given the leader starts with no living teammates and no board tasks
      Then teammate_spawn remains active as the entry point
      And teammate_shutdown, send_message, and task_list are inactive
      And task_create remains active to create the first board item
      And long team orchestration guidance is absent
      When one teammate becomes living
      Then teammate_shutdown and send_message become active
      And long team orchestration guidance becomes active
      When the board has one or more task items
      Then task_list becomes active regardless of living teammates
      When the final teammate stops and the board becomes empty
      Then all conditionally revealed leader controls are removed
      And task_create remains active
      When the leader session shuts down
      Then all conditionally revealed leader controls are removed
      And long team orchestration guidance is absent

  Rule: Leader tool surface is exact

    Scenario: Spawning renders one started line per teammate
      Given the leader spawns a teammate with a kickoff prompt
      When the spawn tool call renders in the transcript
      Then it shows one started line identifying the teammate and kickoff task
      And the line follows the `[agent] @name started · task-name` shape
      And the started line fits the available TUI width with a trailing ellipsis when needed
      And the full result text stays available behind the standard tool rendering
      And a failed spawn keys off the render context isError flag and renders one plain error line

    Scenario: The teammate_spawn started row fits narrow transcript widths
      Given the leader spawns a teammate with a long name and kickoff prompt
      When the started row renders in a narrow transcript
      Then the row stays on one line and does not exceed the available width
      And the kickoff prompt flows into the title uncapped because only the renderer truncates at the actual width

    Scenario: The teammate_spawn started row shows the assignment without duplicate identity or tools
      Given the leader spawns @storm-auditor without a kickoff prompt
      When the started row renders in the transcript
      Then it shows one `@storm-auditor` identity followed by the board-check assignment
      And it does not show the role name a second time as the assignment
      And it does not show the granted tools
      And the collapsed row carries the standard `ctrl+o to expand` hint even when the tool content body is empty but structured details exist
      And expanding the row reveals the full spawn result without tool details

    Scenario: The roster and detail view expose the effective tool allowlist
      Given the leader spawns a teammate from a role definition with tools
      Then the roster records the exact tool allowlist granted to the child process
      And the `/agent-teams` detail view exposes the granted tools when needed for diagnosis
      And the spawn row does not show the granted tools
      And a role derived inline without a tools field shows only the capability set
      And missing read or bash for a file-inspecting assignment remains visible in the roster before another worker turn

    Scenario: Spawning rejects unknown execution-tool ids before any side effect
      Given an agent requesting a tool id pi does not register for teammates
      When the leader attempts the spawn
      Then the spawn fails immediately with no teammate, roster entry, worktree, or persisted role
      And the error names every unknown id instead of silently granting nothing
      And it lists the valid teammate tool universe and explains that the child runs without extensions
      And the universe is exactly the pi built-in tools plus the teammate capability set

    Scenario: Shutting down renders one collapsible agent event line
      Given the leader shuts down a teammate
      When the shutdown tool call renders in the transcript
      Then it shows one event line following the `[agent] @name shut down` shape
      And the collapsed line appends the shared dim expand hint from pi-kit
      And expanding the line reveals the shutdown detail lines such as exit code, released tasks, and usage
      And the event line is never labeled as a monitor event
      And a failed shutdown keys off the render context isError flag and renders one plain error line without an event row

    Scenario: Sending renders one routing line per message
      Given the leader or a teammate sends a message to a living teammate
      When the send_message tool call renders in the transcript
      Then the call slot renders no content of its own
      And the result renders one routing line following the `[message] to @name` shape
      And the line appends exactly one synchronous routing outcome: steered or queued
      And steered means only that the active control stream accepted the message
      And queued means the harness still owns delivery into a recipient turn
      And the collapsed line ends with the standard expand hint and expands to reveal the routing result
      And teammate health never appears as a message routing suffix
      And the full result text stays available to the model without a second transcript row
      And a failed send keys off the render context isError flag and renders one plain error line without an outcome suffix

    Scenario: Reading a terminal report renders a structured message event
      Given a living teammate already sent a terminal report
      When the leader addresses it without reopen=true
      Then no new message is delivered
      And the collapsed row follows `[message] to @name · terminal report available` with the standard expand hint
      And expanding the row reveals the non-delivery reason, duplicate-resend warning, and recorded report
      And expanded detail text wraps to terminal width without omitting any part of the warning or report
      And a missing teammate still renders as one plain error line

    Scenario: Creating a board task renders one created line
      Given the leader creates a board task
      When the task_create tool call renders in the transcript
      Then the call slot renders no content of its own
      And the result renders one `[board] created · <subject>` line truncated to the available width
      And the collapsed line ends with the standard expand hint and expands to reveal the creation result
      And a failed creation keys off the render context isError flag and renders one plain error line without a created row

    Scenario: Every Agent Teams tool uses the shared pi-kit lifecycle renderer
      Given Agent Teams registers leader and worker tools
      When any tool renders a successful result
      Then it uses pi-kit renderToolLifecycle with either started or event semantics
      And its call slot is empty and its result row is width-bounded
      And expanded event details use pi-kit's shared expansion behavior
      And rows carrying detail lines render in pi-kit's shared background style
      And successful rows render inside the shared full-width `[message] from @name` band language, matching the teammate report rows
      And failed results use pi-kit's shared plain error formatting
      And task_list uses the event adapter with the `listed` semantic label

    Scenario: Lifecycle rows survive Pi's class-based Theme
      Given a theme whose bg method reads instance state like Pi's built-in Theme class
      When any tool renders a successful result with details
      Then rendering succeeds without losing the bg receiver
      And detail rows are painted through the bound bg method

    Scenario: Every Agent Teams tool executes through the real tool harness
      Given a fake RPC Pi child and isolated leader and worker state files
      When the leader executes teammate_spawn, teammate_shutdown, send_message, task_create, and task_list
      And the worker executes send_message, task_list, task_claim, and task_submit
      Then every registered Agent Teams tool returns a successful result
      And teammate_spawn starts a child that teammate_shutdown closes
      And the message tools write their expected queue or inbox records
      And the task tools expose the board, claim marker, and submission marker

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

  Rule: Teammate models resolve at spawn time

    Scenario: The inherit alias pins the leader's current model
      Given an agent definition whose model is "inherit"
      And the leader session model is "openai/gpt-5.2"
      When the leader spawns a teammate from that definition
      Then the child launches with --model openai/gpt-5.2
      And the roster records the resolved model on the teammate

    Scenario: An explicit role pin overrides inherit and the team default
      Given an agent definition with model "anthropic/claude-opus-4-6"
      And a team default model of "openai/gpt-5.2" and a leader model of "google/gemini-3-pro"
      When the leader spawns a teammate from that definition
      Then the child launches with --model anthropic/claude-opus-4-6

    Scenario: A role without a model uses the team default model
      Given an agent definition without a model field
      And a team default model set to "openai/gpt-5.2" from the console
      When the leader spawns a teammate from that definition
      Then the child launches with --model openai/gpt-5.2

    Scenario: Without a role model and without a team default no --model flag passes
      Given an agent definition without a model field and no team default model
      When the leader spawns a teammate from that definition
      Then the child launches without a --model flag and Pi picks its default

    Scenario: The inherit alias falls back when the leader has no model
      Given an agent definition whose model is "inherit"
      And the leader session has no current model
      And no team default model is set
      When the leader spawns a teammate from that definition
      Then the child launches without a --model flag

    Scenario: The console sets and clears the unified teammate model
      When the user opens /agent-teams and presses m in the roster page
      Then a searchable model picker lists registry models with type-to-filter
      And every typed character filters the list instead of triggering shortcuts
      And confirming a model stores it as the team default for later spawns this session
      And confirming the pinned clear entry restores Pi's own choice

  Rule: Worktree isolation is an agent-role option

    Scenario: A worktree role owns a git worktree
      Given an agent definition declares worktree: true in a git repository
      When the leader spawns a teammate with that agent
      Then the teammate works in its own worktree on its own branch
      And shutdown captures the diff against the base commit for integration review
      And cleanup removes the worktree directory but keeps the branch so captured work stays retrievable
      And a failed capture commit preserves the worktree directory instead of destroying the work

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
      And each reviewer submits its task with a verify prompt that must pass
      Then completions are gated by the verify reviews rather than self-report
      And the leader synthesizes the final review from the three completed tasks
      And peer challenges never passed through the leader's context
