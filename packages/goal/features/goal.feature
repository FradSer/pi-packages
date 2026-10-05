# The goal runtime contract: a durable objective, one loop, one exit condition.
#
# Every scenario is executed against the real store, ledger, scheduler, and
# completion check — not against a source-text assertion. The harnesses run the
# production modules over the same pi-kit primitives the runtime binds, so a
# change in either package fails here rather than diverging silently.

Feature: Starting a goal

  Scenario: /goal hands the model a seed rather than creating a goal
    Given a session with no goal
    When the user enters /goal followed by a few words
    Then no goal is created by the command
    And the model is asked to write the objective from the conversation
    And the typed words are carried as a quotation, not as the objective

  Scenario: the model can start a goal without being asked
    Given no goal is in flight
    When any request is built
    Then a capability note is injected
    And it names the phrasing a user would type
    And it says when NOT to make a goal out of a request

  Scenario: the model decides whether to create or to revise
    Given a goal is already focused
    When the model is told how to proceed
    Then revising it is offered
    And creating a separate one is named as a different thing

  Scenario: the objective is written by the model
    Given a user asks for a goal in a few words
    When the model creates it
    Then the objective states what must be true when the goal is met
    And a stated requirement is preserved rather than summarised away

Feature: Offline E2E process cleanup

  Scenario: A fixture cannot prevent verification from exiting
    Given an isolated fixture process that ignores SIGTERM
    When the verification ends
    Then cleanup sends SIGKILL after a bounded grace period
    And the process is reaped before success is reported
    Given the fixture already exited
    When cleanup runs
    Then cleanup does not fail or signal another process

Feature: Rejected setting requests preserve pause

  Scenario: A rejected request cannot activate an old internal edit
    Given Pi is processing an old response and the goal is paused
    When the user enters new goal text
    Then the setting request is refused with an idle-retry message
    When the old response revises the objective
    Then the goal remains paused and no resume is recorded
    Given an idle send fails
    When a later internal revision arrives
    Then no activation intent remains

Feature: Accepted requests and completion generations

  Scenario: Asynchronous preflight rejection grants no activation
    Given Pi rejects the setting request before starting the agent
    When a later unrelated revision arrives
    Then the goal remains paused with no resume event

  Scenario: Explicit completion checks cannot close a resumed generation
    Given an explicit completion check has not returned
    When the user resumes the goal
    And the old check returns MET
    Then the resumed goal remains open with its original dispatch

Feature: Explicit goal revision activates work

  Scenario: Setting a new goal request activates its successful revision
    Given this thread's goal is paused
    When the user enters /goal with objective and completion conditions
    And the model successfully revises the goal
    Then the revised goal becomes active with an authorized continuation
    And the status row shows active work instead of paused
    When the model revises text without a new user goal request
    Then the paused state is preserved
    When the thread changes before the revision completes
    Then the old request cannot activate the new thread's goal

Feature: One thread and one command

  Scenario: The single command reads and controls the current thread goal
    Given a thread with one goal
    When /goal is entered without arguments
    Then its current status is displayed without starting work
    And only goal is registered as a slash command
    When /goal pause is entered
    Then the same goal stops and consumes no later usage
    When /goal resume is entered
    Then this thread owns one authorized continuation
    When /goal clear is confirmed
    Then its goal is archived and no continuation survives

  Scenario: Objective text entered while the thread is busy
    Given a goal this thread is pursuing
    And something else is still in flight
    When /goal is entered with a replacement objective
    Then the goal takes the new objective and the run continues on it
    And its objective prose and evidence window move with it
    And the refusal count is reset for the new requirement
    Given a goal this thread is not pursuing
    And something else is still in flight
    When /goal is entered with a replacement objective
    Then the goal is unchanged and the user is told to retry when idle

  Scenario: New threads cannot adopt project goals
    Given another thread has an open goal
    When a fresh thread starts
    Then it has no current goal regardless of old auto-select settings
    When the original thread is restored
    Then its own goal is restored from its entries

Feature: Session start focus

  Scenario: A new session starts unfocused even when a goal is open
    Given a project with one open goal and a session that never focused it
    When the session starts
    Then no goal is focused in the session
    And no status row is shown above the editor
    And no "goal_focused" event is appended

  Scenario: Legacy auto-select settings cannot cross thread boundaries
    Given another thread has one open goal and auto-select was enabled
    When a fresh thread starts
    Then no goal is focused in that thread
    And no status row is shown

Feature: Goal record and durable state

  Scenario: A created goal is durable before any work begins
    When a goal is created with an objective
    Then its record is written atomically under the project goals directory
    And the objective is also readable as user-editable prose
    And a "goal_created" event is appended to the ledger
    And no ledger event is appended when the record write fails

  Scenario: Re-reading the pool finds every open goal and ignores malformed files
    Given three open goals and one malformed file in the goals directory
    When the goal pool is read
    Then three goals are returned in a deterministic order
    And the malformed file is ignored rather than failing the scan
    And a symlinked entry is never followed

  Scenario: A record from disk wins over stale memory
    Given an open goal loaded into memory
    And the record on disk was changed by another process
    When the goal is mutated
    Then the mutation starts from the record on disk
    And the revision on disk is incremented by exactly one

  Scenario: Concurrent writers produce a conflict rather than a lost update
    Given two processes hold the same goal at the same revision
    When both write
    Then exactly one succeeds
    And the other is refused naming the expected and actual revision
    And the refused write changes nothing on disk

  Scenario: Real processes racing for one goal produce one winner
    Given eight real processes that all read the same revision before any writes
    When all eight write concurrently
    Then exactly one succeeds and the record advances exactly once

  Scenario: A writer whose lock was taken from it writes nothing
    Given a write whose lock is taken while the change is being prepared
    When the write is about to land
    Then it is refused and nothing is written over the new holder

  Scenario: A completed goal is archived and leaves the open pool
    When a goal is completed and archived
    Then it no longer appears in the open goal pool
    And the archived record remains readable
    And a "goal_completed" event is appended
    And the completing event lands in the archived ledger, not a new open one

  Scenario: There is one exit condition, not two
    Given a goal with an objective and a completion contract
    When completion is considered
    Then only the contract and the evidence are consulted
    And no second opinion about progress can contradict the first

Feature: Ledger

  Scenario: Events append in order and read back in order
    Given a fresh goal ledger
    When five lifecycle events are appended
    Then reading the ledger returns those five events in append order
    And each event carries its goal id and a timestamp

  Scenario: A malformed record is consumed and reported, never blocking the drain
    Given a ledger whose second line is not JSON
    When the ledger is read from offset zero
    Then the well-formed records are still returned
    And the malformed record is reported as a diagnostic
    And the returned offset resumes after the last complete record

  Scenario: History paging never reads a partial record
    Given a ledger with more records than one batch cap
    When history is read page by page
    Then every page contains only complete records
    And the final page contains the remaining records exactly once

  Scenario: Lifecycle state rebuilds from the ledger alone
    Given a goal whose record is lost
    When it is rebuilt from its ledger
    Then its lifecycle status and reason are recovered

Feature: The loop

  Scenario: Automatic continuation is unlimited by default and bounded on request
    Given a new goal
    When scheduling decisions are claimed repeatedly
    Then every claim is authorized
    When a run allowance is configured
    Then claims stop once the allowance is spent
    And the refusal names the setting that stops them

  Scenario: A claim must match the generation that armed it
    Given a ready scheduling decision
    When the goal is mutated between arming and claiming
    Then the claim is refused
    And no run is counted
    And the goal is paused naming the stale generation

  Scenario: Only one claim consumes one decision
    Given an armed scheduling decision
    When the claim is attempted twice
    Then the first succeeds
    And the second is refused

  Scenario: A claim armed for one goal cannot be spent on another
    Given a decision armed for one goal
    When focus moves to another goal before the claim lands
    Then the claim is refused
    And the newly focused goal is neither dispatched nor paused

  Scenario: Losing the race to claim stands down
    Given two schedulers on the same owner have armed one decision
    When both claim it
    Then exactly one run is consumed
    And the loser does not pause a goal whose run is in progress

  Scenario: Work tools are blocked after a decision ended the turn
    Given a scheduling decision was saved during the current turn
    When the model calls a work tool later in the same turn
    Then the call is blocked naming the decision
    And reading the goal remains allowed

  Scenario: Saving a next action does not itself consume a run
    Given an active goal with a fresh run allowance
    When the model saves its next action
    Then the goal is ready to continue
    And the run count is unchanged
    And the turn ends so the action cannot be invalidated by further work
    And a saved note for a goal that cannot continue is refused with its reason

  Scenario: The loop itself decides whether the goal is met
    Given an execution that ended without asking for completion
    When the turn settles
    Then the completion check runs on its own
    And an answer of MET archives the goal without another run
    And anything else becomes the next turn's input

  Scenario: A background failure does not take the runtime down
    Given a continuation queued on a timer
    When the session reloads underneath it
    Then the stale context does not produce an unhandled rejection

Feature: Three unsuccessful final attempts

  Scenario: Final attempts stop with specific guidance after three refusals
    Given this thread's goal is active
    When three explicit completion requests receive valid NOT MET verdicts
    Then the goal pauses and its continuation is cancelled
    And the response names the last unmet condition
    And it advises how to supply missing observations or rerun a failed check
    And no goal_completed event is recorded
    When requirements are revised or the user resumes
    Then the refusal count resets
    When an old cancelled verdict returns
    Then it does not consume a final attempt

Feature: Completion evidence and bounded empty continuation

  Scenario: Observed results establish completion without executor self-certification
    Given current-thread tool output and an independent review result
    When completion is checked
    Then their provenance and outcomes reach the tool-less checker separately from the executor claim
    And user text pretending to be a tool result is not evidence
    And a changed completion contract excludes earlier observations
    When the checker returns MET
    Then the goal is complete and archived, its widget is removed, and no continuation remains

  Scenario: Empty turns cannot continue indefinitely
    Given an active goal whose check returns NOT MET
    When three consecutive runs perform no work
    Then the runtime stops automatic continuation with a single explanation
    And it does not report the goal as complete
    When real work succeeds and the objective is proven
    Then completion remains available and is not replaced by pause

Feature: The completion check

  Scenario: The check cannot act on the work it is judging
    When the check runs
    Then it is granted no tools at all
    And it has no session, no extensions, and no skills
    And nothing it is given lets it read or change the workspace

  Scenario: The verdict is the report's last line, or there is no verdict
    Given a check report in each of these forms: a trailing marker, a marker
      followed by more text, a marker mentioned in prose, and no marker at all
    When each is parsed
    Then only the trailing marker approves
    And every other form rejects, with the executor told what to do

  Scenario: The executor's completion claim is never evidence
    Given a goal whose objective is unsatisfied
    And an executor completion claim asserting it is satisfied
    When the check runs
    Then the claim is presented as untrusted
    And an unproven claim is not proof

  Scenario: A refused completion leaves the goal open
    Given a check that says the objective is not met
    When the model asked for completion
    Then the goal stays open
    And the executor is told what is still missing
    And nothing is archived

  Scenario: An accepted completion archives the goal
    Given a check that says the objective is met
    When the model asked for completion
    Then the goal is archived
    And the verdict is recorded before the archive

  Scenario: Archiving waits for the verdict
    Given a completion request whose check has not returned
    When the request is in flight
    Then the goal is still in the open pool

  Scenario: The check can be switched off, and the skip is recorded
    Given checking is disabled in settings
    When the model asks for completion
    Then completion proceeds without a check
    And the skipped check is recorded in the ledger

  Scenario: A check that cannot be trusted is a refusal
    Given the check exits with an error
    Or the check returns nothing
    Or the check floods its output past the size bound
    Or the check hangs and is cancelled
    Then the goal is not accepted
    And the failure is reported rather than silent

  Scenario: The objective and the claim cannot close their own blocks
    Given an objective that tries to close its own injection block
      with an instruction behind it
    When the prompt is built
    Then exactly one real closing tag survives
    And the attempt arrives escaped, with its text still delivered
    Given an objective containing the closing delimiter
    When the check prompt is built
    Then the text stays inside its block
    And the real delimiter appears exactly once

Feature: Research file safety

  Scenario: Existing symbolic links cannot redirect goal files
    Given a linked prompt file or goal parent directory
    When creation is attempted
    Then creation is refused before any outside write
    Given a linked research file or parent directory
    When research is read
    Then no outside content is returned

Feature: Research before creation

  Scenario: A read-only worker gathers the material for an objective
    Given no goal exists yet
    When the model calls research_goal
    Then a child process explores the workspace with read, grep, find, and ls only
    And it has no bash, no session, and no extensions
    And its findings are returned to the model as material, not as a decision
    And no goal file is written before creation

  Scenario: Findings attach to the goal created from them
    Given research findings are waiting in this session
    When the model creates a goal
    Then the findings are written into the goal directory
    And the research tokens are charged to the goal
    And a "research_attached" event follows "goal_created" in the ledger
    And get_goal can read the findings back
    When a second creation is requested in the same thread
    Then creation is refused and the first goal remains current

  Scenario: Research runs on its configured model
    Given a research model is set in the settings
    When research runs
    Then the child is started with that model
    And the completion check keeps its own model

  Scenario: A failed research never blocks creation
    Given the research worker fails or returns nothing
    When the model creates a goal anyway
    Then the goal is created without research material
    And the failure is reported rather than silent

  Scenario: The latest successful research is what attaches
    Given one successful research in this session
    When a later research fails
    Then the earlier findings still wait for the next goal
    When another research succeeds
    Then the second findings replace the first

  Scenario: Research does not survive a session boundary
    Given research findings are waiting in this session
    When the session is restored at a boundary
    Then the findings are dropped
    And the next goal is created without them

  Scenario: Research is work, not recall, after a decision ended the turn
    Given a saved next action ended the current turn
    When the model calls research_goal later in the same turn
    Then the call is blocked naming the decision
    And reading the goal remains allowed

  Scenario: Research material never reaches the completion check
    Given a goal with attached research
    When the completion check prompt is built
    Then it carries the objective, the contract, the claim and the recorded observations
    And the research findings are not part of it

Feature: Below-editor status and minute display

  Scenario: Goal activity stays below the editor
    Given a current goal with less than one minute of recorded work
    When the shared Pi widget is rendered
    Then it mounts below the input editor
    And the elapsed time is 0m with no seconds suffix
    Given more than one hour of recorded work
    When the elapsed time is displayed
    Then it uses hours and minutes
    Given more than one day of recorded work
    When the elapsed time is displayed
    Then it uses days and hours

Feature: What the surface shows

  Scenario: Elapsed time is the progress a goal reports
    Given a goal that has been running for some time
    When its state is displayed
    Then the elapsed time is shown
    And no fraction of an imagined list is shown

  Scenario: Injected state does not disturb the prompt cache
    Given goal state is injected at the tail of each request
    When two consecutive requests are built
    Then the first is a true prefix of the second
    And every note already sent is replayed verbatim at the index it was sent from
    And replayed notes are bounded rather than accumulating per turn
    And filling the window costs one break and the turn after it is stable again

  Scenario: Stable policy is separated from per-turn counters
    When two consecutive turns inject goal state
    Then the policy block is byte-identical between them
    And only the counter block differs

  Scenario: The persisted continuation marker carries no goal text
    When a continuation turn is persisted
    Then the persisted marker is bounded and contains only the goal id
    And the authoritative state is injected at request time instead

  Scenario: Omitted requirements are retrievable rather than silently lost
    Given an objective longer than the prompt budget
    When the goal state is injected
    Then the truncation is stated
    And the model is told how to retrieve the remainder

  Scenario: A command tells the user what happened
    Given a goal was paused
    When the user runs a command
    Then the outcome is reported to them
    And the durable state agrees with what they were told