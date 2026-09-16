@design @unimplemented
Feature: Advanced Work management behind three coordination tools
  This is the next design contract, not the behavior of the installed extension.
  Agent delegation and board scheduling use the same Work Item lifecycle.

  Rule: Final cutover removes legacy tools only after replacement behavior exists

    Scenario: Final tool removal is an atomic replacement cutover
      Given strict Agent actions, complete Work operations, and communication-only Agent Event are replacement-tested
      And automatic and explicit Work submissions share one attempt-aware acceptance pipeline
      And runtime grants, disclosure, prompts, Console, documentation, and snapshot handling no longer teach legacy tools
      When the final public interface is registered
      Then leader and Worker active tool maps contain only agent, work, and agent_event for their authorized states
      And no legacy tool name is registered, granted to a child, or named by active guidance
      And incompatible runtime snapshots fail explicitly rather than silently migrating

  Rule: Agent actions replace resident lifecycle tools

    Scenario: Agent delegate accepts an inline session definition
      Given no filesystem definition exists for an Agent name
      When the Leader calls agent delegate with a prompt and inline definition
      Then one independent Work Item and Work Session start
      And the definition is session-local unless persist is explicitly true
      And the receipt contains the Work ID, Assignment Attempt, and incarnation-bound session handle

    Scenario: Agent start creates an unassigned resident
      Given a defined or inline Agent definition
      When the Leader calls agent start
      Then one resident starts without a Work Item or Assignment Attempt
      And its receipt contains an incarnation-bound session handle

    Scenario: Agent inspection uses an exact incarnation handle
      Given an Agent has current and stopped Work Sessions with different incarnations
      When the Leader calls agent inspect with one returned session handle
      Then it returns only that matching current session
      And a stale or role-mismatched handle rejects without affecting a resident

    Scenario: Agent stop targets only its returned incarnation
      Given a resident name has been reused by a replacement Work Session
      When the Leader calls agent stop with the earlier incarnation handle
      Then the replacement remains alive
      And the stale handle rejects without releasing the replacement's Work

  Rule: Each operation has one owner

    Scenario: The coordination interface has three tool names
      When the next interface is registered
      Then the coordination tools are agent, work, and agent_event
      And legacy teammate and task tools and send_message are absent
      And each caller receives only the operations permitted by its role and current state

    Scenario: Ordinary delegation uses the same work lifecycle as explicit scheduling
      Given a defined Agent and one assignment
      When the Leader delegates it in one agent call
      Then one Work Item and one Assignment Attempt are created
      And one independent Work Session starts with that assignment
      And work list exposes the same Work Item, ownership, resources, and verification policy

    Scenario: Direct and autonomous Work acquisition share resource authority
      Given ordinary delegation owns resource "firmware/storage"
      When an eligible resident claims pending work for "firmware/storage/mounts"
      Then the claim is rejected until the direct Work Item safely settles or releases

    Scenario: Delegating twice to one Agent starts independent work
      Given an Agent already owns active work
      When the Leader delegates another prompt without selecting a resident session
      Then a different Work Item, Assignment Attempt, and Work Session are created
      And the first Work Session receives no extra kickoff

    Scenario: Generated roles need an explicit definition but not a second tool
      Given an Agent name has no definition
      When the Leader delegates with a valid inline definition
      Then the role is registered for the current runtime and work starts in the same call
      But when the definition is missing the operation fails before creating work or execution
      And no definition is persisted without an explicit user request

    Scenario: An unassigned resident does not promise a work result
      When the Leader explicitly starts a resident without work
      Then no Work Item or Assignment Attempt is fabricated
      And the result identifies the resident session without promising completion
      And an idle resident consumes no model turns until actionable mail or a claimable-work notice arrives

    Scenario: Inspection reads state without creating a waiting protocol
      Given active and idle Work Sessions and a completed Work Item
      When the Leader deliberately inspects Agent Presence or lists work
      Then the result is a bounded state projection with precise handles
      And inspection starts no process or model turn and cannot prove message consumption
      And a completed result can be read without asking a Worker to resend it

  Rule: The ledger authorizes work

    Scenario: Leader creates and lists one pending Work Item through the Work interface
      Given no Work Item exists
      When the Leader calls work create with dependencies, resource tags, and a verification gate
      Then the receipt identifies one pending Work Item with normalized resources and its verification policy
      And the receipt uses Work terminology without directing a legacy task operation
      And no resident or Work Session starts
      When the Leader calls work list
      Then the same Work Item appears with its ID, dependencies, resources, and pending state

    Scenario: Work create rejects an unknown dependency without partial state
      Given no Work Item exists
      When the Leader calls work create with an unknown dependency
      Then the operation fails before creating a Work Item or starting a resident

    Scenario Outline: Work action schemas reject fields owned by another action
      Given the Leader uses the Work interface
      When it sends <payload>
      Then validation rejects the request before calling a Work operation

      Examples:
        | payload                                                    |
        | list with a subject                                        |
        | create with supersedes                                    |
        | create with an undeclared field                           |

    Scenario: Creating unassigned work does not spawn a process
      When the Leader creates a Work Item with dependencies and resource tags
      Then it remains pending until an explicit assignment or accepted resident claim
      And only eligible idle residents receive a bounded claimable-work notice

    Scenario: Assignment requires an exact eligible session target
      Given pending work with satisfied dependencies and available resources
      When the Leader assigns it to an exact idle session route
      Then the ledger authorizes one Assignment Attempt before its work starts
      And an occupied session, unknown route, unmet dependency, or conflicting resource fails without partial assignment

    Scenario: Leader assigns pending Work to a named Agent for fresh execution
      Given a defined Agent and one pending Work Item
      When the Leader calls work assign with that Work ID and the Agent name
      Then the runtime starts one generated Work Session for that Agent
      And the pending Work Item becomes claimed by that exact new session
      And the Work Item keeps its ID, dependencies, resources, and verification policy

    Scenario: Named Agent assignment releases Work when fresh execution cannot start
      Given a defined Agent and one pending Work Item
      When the named Agent process fails after the Work Item is bound
      Then the same Work Item remains pending with an actionable failure reason
      And no generated resident retains ownership or a resource lock

    Scenario: Leader assigns pending Work to an exact idle session
      Given an idle resident and one pending Work Item with resource tags
      When the Leader calls work assign with that Work ID and the resident's precise session route
      Then the same Work Item becomes claimed by that resident
      And it receives a new Assignment Attempt with the Work Item resources
      And the runtime starts a fresh Pi session before delivering the Work Item description

    Scenario: Worker queues one Work claim through the Work interface
      Given an eligible resident has one claimable Work Item
      When it calls worker work claim with that Work ID
      Then the receipt reports one queued Work claim intent rather than ownership
      When the runtime accepts that intent
      Then the Work Item becomes claimed by that resident
      And the runtime starts a fresh Pi session before delivering the Work Item

    Scenario: Worker Work claim schema rejects legacy and leader fields
      Given a resident has a Worker Work interface
      When it supplies taskId, target, subject, or another action to work claim
      Then request validation rejects it before a claim intent is written

    Scenario: Claim intent is not ownership
      Given two eligible residents request the same pending Work Item
      When the runtime resolves their claims
      Then exactly one resident receives an accepted ownership binding
      And neither resident starts the work before authoritative acceptance
      And the losing resident receives an actionable rejection without polling

    Scenario: Busy work from either entry point shares the same resource guard
      Given delegated work owns resource "firmware/storage"
      When another resident claims work for "firmware/storage/mounts"
      Then the claim is rejected until the original authority is safely released

    Scenario: Failed Work requires an explicit retry decision
      Given a current Assignment Attempt fails or its process exits unexpectedly
      And no release or supersession intent was already accepted
      When the failure is recorded
      Then the Work Item becomes pending with its failure reason rather than completed or silently retried
      And dependents remain blocked until a later assignment accepts it
      And the Leader retries it through exact-session assignment or autonomous claim

    Scenario: Leader reopens completed Work through the Work interface
      Given a completed Work Item with no active dependent authority
      When the Leader calls work reopen with that Work ID and a reason
      Then the same Work Item becomes pending without starting a Worker
      And its prior result is cleared from current Work state
      And a later exact-session assignment creates a new Assignment Attempt

    Scenario: Work reopen rejects unsupported current holdings
      Given a pending, claimed, superseded, or verification-held Work Item
      When the Leader calls work reopen
      Then the operation rejects without changing ownership, resources, or result evidence

    Scenario: Work reopen rejects an active direct or indirect dependent
      Given completed Work Item A has a direct or indirect claimed dependent
      When the Leader calls work reopen for A
      Then the operation rejects and identifies the blocking dependent Work Item
      And A remains completed and the dependent retains its authority

    Scenario: Reopening keeps completed Work identity and replaces current evidence
      Given completed Work whose direct and indirect dependents have no active or retained authority
      When the Leader explicitly reopens it
      Then the same Work Item becomes pending without spawning or messaging a Worker
      And its prior current result is cleared before a later Assignment Attempt
      And ordinary messages and old completion evidence cannot authorize that later assignment

    # Failed Work is already pending after release. Claimed parked Work requires
    # a future machine-owned retirement transition and is rejected by work reopen.

    Scenario Outline: Reopening a prerequisite rejects live dependent authority
      Given Work Item A is completed
      And a direct or indirect dependent B is <condition>
      When the Leader attempts to reopen A
      Then the operation rejects and identifies B as a blocking dependent
      And A retains its acceptance and lifecycle state
      And B retains its existing ownership and resources

      Examples:
        | condition                              |
        | active                                 |
        | verifying                              |
        | verification-parked                    |
        | revoked but still retaining resources  |

    Scenario: Reopening and acquiring a dependent share one atomic guard
      Given A is completed and its dependent B is pending
      When the Leader reopens A concurrently with an assignment or claim of B
      Then either B acquires authority and reopening A rejects
      Or A becomes pending and B cannot acquire authority against the old acceptance
      And no ordering leaves A reopened with a newly authorized dependent

    Scenario: Reopening preserves accepted downstream history
      Given A and its dependent B are completed without live holdings
      And C depends on B and has not started
      When the Leader reopens A
      Then B and its accepted evidence remain historical completed work
      And assignment or claim of C rejects until A is accepted again
      And acquisition checks the current acceptance of indirect as well as direct prerequisites

    Scenario: Leader supersedes Work through the Work interface
      Given unfinished Work Item A with a pending dependent
      When the Leader calls work supersede with a replacement Work description
      Then the replacement Work Item is pending with a new stable ID
      And A becomes superseded and the dependent references the replacement
      And no active holder loses resource authority until cancellation acknowledgement or confirmed stop

    Scenario: Work supersede rejects a completed or unknown Work Item
      Given a completed or unknown Work Item
      When the Leader calls work supersede
      Then the operation rejects before creating a replacement Work Item

    Scenario: Supersession does not release a live writer early
      Given active work holds a resource and has pending dependents
      When the Leader replaces it through work supersede
      Then the replacement and dependency rewrites are recorded atomically
      And obsolete work cannot be claimed or completed
      And its resource authority remains until bound cancellation acknowledgement plus authoring settlement or confirmed process stop
      And stale submissions cannot release the replacement's resources

    Scenario: Supersession invalidates a terminal submission awaiting settlement
      Given a direct Work Item submitted a terminal result but authoring has not settled
      When the Leader supersedes that Work Item
      Then its pending submission is invalidated before settlement
      And settlement cannot start a verification gate for the superseded Work Item
      And cancellation feedback remains the only authorized next execution for its holder

    Scenario: A retained superseded holding blocks another reclaim by its owner
      Given a Worker retains a superseded Work Item and its resources pending cancellation acknowledgement
      When the Leader tries to reclaim different pending Work for that Worker
      Then the operation rejects without replacing the retained current Work handle
      And the superseded Work Item keeps its resource authority

    Scenario: Release acknowledges supersession without resurrecting work
      Given a superseded Work Item still has a live revoked owner
      When its bound owner releases the holding and the authoring execution settles
      Then only that old holding and its resources are released
      And the Work Item remains superseded with its replacement reference intact
      And no pending work or successful submission is fabricated for the obsolete item

    Scenario: Leader releases claimed Work through the Work interface
      Given a Leader owns one claimed Work Item through a resident
      When it calls work release with that Work ID and a reason
      Then the Work Item becomes pending with the release reason
      And the owner and resources are released without claiming completion
      And pending or completed Work cannot be released

    Scenario: Release invalidates verification before relinquishing the holding
      Given S1 is being verified for a settled frozen owner
      When the Leader releases the holding
      Then the runtime retires S1 verification authority before making the Work Item pending
      And resources are safely released without waking the owner for acknowledgement
      And a delayed PASS for S1 cannot complete the pending Work Item

    Scenario: Stopping execution does not count as completing work
      Given a resident owns active or verifying work with no prior release intent
      When the Leader stops its exact session
      Then no successful work result is fabricated
      And resource authority survives until stop is confirmed
      And confirmed stop retires the holding and leaves the Work Item failed with a stopped reason
      And stop failure leaves the ownership and stop intent visible without making the work claimable

    Scenario: A pending stop invalidates a concurrent review result
      Given S1 is being verified
      When the runtime accepts a stop request for its owner before receiving PASS for S1
      Then PASS for S1 is stale and cannot complete work or release resources
      And the Work Item stays owned until stop is confirmed
      And confirmed stop leaves the Work Item failed

    Scenario: Stop confirmation completes a previously accepted release
      Given the Leader requested release of a running owner and its resources remain held
      When that exact session is confirmed stopped
      Then the runtime completes the pending release and makes the Work Item pending
      And it does not replace the release outcome with a failed or completed result

    Scenario: Stop confirmation preserves superseded and completed work
      Given a session has a superseded holding or previously completed work
      When the Leader stops the exact session and stop is confirmed
      Then any retained superseded holding is retired without making its Work Item pending
      And previously completed work and its evidence stay completed

  Rule: Submission and acceptance are different

    Scenario: Direct automatic submission honors the Work Item verification gate
      Given ordinary delegation created a claimed Work Item with a verification gate
      When the current owner produces its ordinary final answer and execution settles
      Then the result enters that Work Item verification path
      And the Work Item remains claimed until a passing gate accepts it
      And a passing gate completes the Work Item and releases its owner and resources

    Scenario: A failed direct verification authorizes one Work revision
      Given a direct Work Item's current automatic submission fails its first verification gate
      When the runtime returns the gate findings to the current owner
      Then the Work Item remains claimed with resources retained
      And the runtime authorizes a new direct Assignment Attempt for the same Work ID
      And the owner can submit one revised automatic result without Leader reopen
      And a late PASS for the failed submission cannot complete the revision

    Scenario: A failed direct result releases its claimed Work Item
      Given a direct Work Item is claimed by its current owner
      When that owner reports a failed terminal result
      Then the Work Item becomes pending with its failure reason
      And the owner and its resources are released

    Scenario: Direct retry reclaims the released Work Item
      Given a failed direct Work Item is pending with its original resource tags
      When the Leader directs that exact Work ID to retry
      Then the runtime reclaims the same Work Item with a new direct Assignment Attempt
      And the new owner retains the Work Item resources
      And its next automatic result submits to that Work Item rather than an untracked assignment

    Scenario: First direct message to an unassigned resident creates Work
      Given a resident has no current Work Item
      When the Leader sends its first direct assignment message
      Then the runtime creates and claims one Work Item using that resident's stable Work ID
      And the owner and resource record bind to the new direct Assignment Attempt
      And its terminal result enters the same Work lifecycle rather than an untracked assignment

    Scenario: Automatic and explicit submissions share one acceptance pipeline
      Given a Worker owns a Work Item with a verification gate
      When it finishes with an ordinary final answer or explicitly submits a result through work
      Then the current Assignment Attempt supplies one submission
      And verification starts only after the authoring execution settles
      And the Work Item cannot complete or unblock dependents until verification passes

    Scenario: Steering cannot mutate a submission under review
      Given the owner submitted S1 and its authoring execution settled
      And S1 is being verified with the owner frozen
      When a Leader steer or peer message arrives before PASS for S1
      Then the message is retained as deferred mail bound to the current attempt
      And no owner execution resumes and the reviewed files are not changed through message delivery
      And PASS may accept S1 while the deferred message becomes historical
      And the Work result exposes the deferred-mail reference without automatically reopening work

    Scenario: Already queued execution cannot bypass the verification gate
      Given a message is already queued for owner execution when a submission is recorded
      When the runtime prepares to verify the submission
      Then it prevents queued delivery from starting another owner turn
      And verification starts only after queued execution and in-flight authoring are confirmed quiescent
      And inability to confirm quiescence leaves acceptance pending rather than accepting stale evidence

    Scenario: Mail arriving after a terminal submission remains historical at settlement
      Given a direct owner submitted a terminal result but its authoring execution has not settled
      When peer or harness mail arrives before settlement
      Then it remains deferred and cannot start another authoring turn
      When the authoring execution settles
      Then the runtime archives the deferred mail before starting verification
      And verification cannot inspect files changed by that deferred mail

    Scenario: Unexpected owner execution invalidates a running review
      Given S1 is being verified while owner execution is frozen
      When the runtime observes unexpected owner execution
      Then S1 verification authority is invalidated before a PASS can be applied
      And the holding stays reserved with one actionable attention event
      And no new submission or automatic retry is authorized by that event
      And only an explicit Leader recovery direction can authorize a revision
      And that direction preserves the Work ID and resources while replacing the direct Assignment Attempt

    Scenario: Worker submits owned Work through the Work interface
      Given a Worker owns a claimed Work Item
      When it calls worker work submit with a success result
      Then the receipt reports a queued Work submission rather than completion
      When the authoring execution settles and the runtime accepts that submission
      Then the Work Item completes only after its effective verification gate passes
      And a failed outcome releases the Work Item with its failure result

    Scenario: Explicit submission suppresses the duplicate automatic submission
      Given a Worker explicitly submits the result of its current Assignment Attempt
      When its execution later settles
      Then the same result is not submitted, verified, or announced twice

    Scenario: Tool progress and unassigned answers are not submissions
      When execution emits tool progress, a retry, or an answer without a current Assignment Attempt
      Then no Work Item is completed and no fabricated submission is recorded

    Scenario: A first failed review returns findings to the same owner
      Given the current submission fails its effective verification gate
      And the runtime retained deferred mail for that attempt
      When this is the first rejection for the holding
      Then the runtime invalidates the old verification authority and authorizes a revision before waking the owner
      And the Work Item remains owned with resources retained
      And the Worker receives findings and still-applicable deferred mail and may make a new submission
      And the old submission's delayed verification cannot accept the new one

    Scenario: Repeated or inconclusive verification requests a decision
      Given verification fails twice or remains inconclusive after one clarification
      When the runtime parks the holding
      Then the current owner and resources remain reserved
      And one attention event reaches the Leader
      And an inconclusive verdict is not recorded as a defect or a successful completion
      And more automatic submissions remain blocked until explicit Work control resolves the holding
      And ordinary mail is retained but cannot resume the owner or clear the parked reason

    Scenario: Completion is independent of how the work was acquired
      Given a Worker acquired work by direct delegation, explicit assignment, or autonomous claim
      When the current submission is accepted without a gate or passes its gate
      Then one completed result with work and attempt identity reaches the Leader
      And resources are released only after the authoring execution has settled
      And the resident becomes eligible for later claimable-work notices

  Rule: Communication does not control the lifecycle

    Scenario: All participants use one messaging operation
      Given a Leader and two Work Sessions with bound identities
      When they exchange information or requests
      Then each uses agent_event with the same recipient and message meanings
      And sender identity and assignment authority come from the runtime
      And only a unique bound reply route permits an omitted recipient

    Scenario: Messages cannot submit or reopen work
      Given a Work Item is active or terminal
      When an ordinary message claims that work is done or asks it to continue
      Then it does not change work ownership, verification, or lifecycle state
      And terminal-status and reopen controls are not accepted message parameters

    Scenario: Delayed mail remains bound to its original attempt
      Given an event targets the current attempt of a Work Item
      And that attempt closes before the event is consumed
      When the Work Item is reopened and assigned again
      Then the old event is historical or rejected rather than delivered as guidance to the new attempt

    Scenario: Coordination guidance is not copied into every receipt
      When a start, message, or Work control operation succeeds
      Then its receipt reports state, synchronous acceptance, and any pending next actor concisely
      And detailed transport states remain available for diagnostics
      And the shared Leader policy directs independent work or yielding until automatic results arrive
      And runtime behavior does not depend on interpreting the wording of a status request
