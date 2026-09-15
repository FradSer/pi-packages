@design @unimplemented
Feature: Advanced Work management behind three coordination tools
  This is the next design contract, not the behavior of the installed extension.
  Agent delegation and board scheduling use the same Work Item lifecycle.

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

    Scenario: Creating unassigned work does not spawn a process
      When the Leader creates a Work Item with dependencies and resource tags
      Then it remains pending until an explicit assignment or accepted resident claim
      And only eligible idle residents receive a bounded claimable-work notice

    Scenario: Assignment requires a precise eligible target
      Given pending work with satisfied dependencies and available resources
      When the Leader assigns it to an exact idle session or a defined Agent for fresh execution
      Then the ledger authorizes one Assignment Attempt before its work starts
      And an occupied session, unavailable definition, or conflicting resource fails without partial assignment

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
      Then the Work Item is failed rather than completed or silently requeued
      And dependents remain blocked
      And the Leader can explicitly reopen it or release eligible unfinished work back to pending

    Scenario: Reopening keeps work identity and replaces completion evidence
      Given completed, failed, or verification-parked work whose execution has settled
      And no dependent has active execution or retained authority
      When the Leader explicitly reopens it
      Then the same Work Item becomes pending without spawning or messaging a Worker
      And its previous result remains historical
      And its next assignment receives a new Assignment Attempt
      And ordinary messages and old completion evidence cannot authorize that assignment

    Scenario: Reopening a parked holding retires its authority atomically
      Given verification-parked work has a settled frozen owner and retained resources
      And no affected dependent has active execution or retained authority
      When the Leader reopens the Work Item
      Then the runtime atomically retires the old holding and submission authority and releases its resources
      And the same Work Item becomes pending without a separate release call
      And deferred mail remains historical rather than waking the old owner
      And no new attempt or process starts until assign or claim is accepted

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

    Scenario: Supersession does not release a live writer early
      Given active work holds a resource and has pending dependents
      When the Leader replaces it through work supersede
      Then the replacement and dependency rewrites are recorded atomically
      And obsolete work cannot be claimed or completed
      And its resource authority remains until bound cancellation acknowledgement plus authoring settlement or confirmed process stop
      And stale submissions cannot release the replacement's resources

    Scenario: Release acknowledges supersession without resurrecting work
      Given a superseded Work Item still has a live revoked owner
      When its bound owner releases the holding and the authoring execution settles
      Then only that old holding and its resources are released
      And the Work Item remains superseded with its replacement reference intact
      And no pending work or successful submission is fabricated for the obsolete item

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

    Scenario: Unexpected owner execution invalidates a running review
      Given S1 is being verified while owner execution is frozen
      When the runtime observes unexpected owner execution
      Then S1 verification authority is invalidated before a PASS can be applied
      And the holding stays reserved with one actionable attention event
      And no new submission or automatic retry is authorized by that event

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
