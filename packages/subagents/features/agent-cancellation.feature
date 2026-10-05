Feature: Cancelling a tool wait never invents a process outcome

  Rule: Cancellation before dispatch has no effects

    Scenario: An already aborted invocation cannot create or control a child
      Given an aborted tool signal
      When a startup, input or stop operation is invoked
      Then the tool returns a cancelled refusal before dispatch
      And no process, input, role, workspace or roster mutation occurs

    Scenario: Cancellation during the reservation callback retains its exact intent
      Given agent_start has committed a new exact roster reservation before native setup
      When a roster observer cancels the caller's tool wait
      Then the caller receives that reservation handle and a pending startup intent
      And setup still settles the same reservation without an orphan or retry

  Rule: An in-flight control owns its eventual acknowledgement

    Scenario: Cancellation while startup confirmation is pending
      Given agent_start already dispatched and its exact child is awaiting acknowledgement
      When the caller cancels the tool wait
      Then the tool returns promptly with cancelled and the exact handle when known
      And it reports the observed state and pending start intent without claiming input rejection
      And native acknowledgement and authoritative progress continue to settle that original child
      And no replacement or termination is triggered by caller cancellation

    Scenario: A positive late acknowledgement leaves the same child usable
      Given a cancelled startup wait with the original child still retained
      When its positive acknowledgement arrives
      Then the same exact incarnation becomes usable
      And subsequent caller cancellation does not end its lifetime
      And its settled answer is delivered exactly once

    Scenario: Cancelled next or steer waits retain uncertain authority
      Given next or steer input already dispatched to an exact resident
      When its tool wait is cancelled before acknowledgement
      Then no second input, new process or guessed idle restoration occurs
      And the original acknowledgement or authoritative progress remains responsible for the outcome

    Scenario: A cancelled stop wait still completes the committed close
      Given agent_stop intent recorded on an exact child
      When the caller cancels the close wait
      Then the tool reports cancelled with pending stop intent
      And late closure confirmation retires only that exact incarnation
      And an unconfirmed closure retains stop intent and control authority

    Scenario: A hosted reservation is closable before its acknowledgement
      Given a hosted agent_start reserved a living exact incarnation and is awaiting confirmation
      When the caller cancels its startup wait and explicitly stops that exact handle
      Then stop reaches the host that made the reservation
      And late startup confirmation cannot reinstall retired bindings or revive the stopped child
      And cancelling the wait alone sends no stop

    Scenario: A late hosted confirmation cannot rebind a same-name successor
      Given a cancelled hosted startup pinned its original reservation and control owner
      And a different host started a same-name replacement after confirmed closure
      When the original startup response names either the old handle or the successor handle
      Then its confirmation is refused without changing the successor's state or control owner
      And later input and stop controls reach only the successor's own host

    Scenario: Synchronous reentrant startup cannot seize an owned successor
      Given host A reserved and closed its original incarnation during its start call
      And a reentrant start reserved a same-name successor before A returned
      When A samples the roster for its eager binding
      Then an already-owned exact record is not accepted as A's reservation
      And no existing binding is overwritten even when both starts use the same host object
      And A's cancellation or failure never names the successor as its own handle
      And the successor's confirmation, state and explicit controls retain their actual owner

    Scenario: Startup confirmation has no fallback to an unrelated living record
      Given a host returns a live handle without reserving a new incarnation for this start
      When confirmation is checked
      Then startup is refused without claiming acceptance
      And existing control ownership and roster facts remain unchanged

    Scenario: Returned late control failures remain diagnostic evidence
      Given an exact input or stop already dispatched and its caller stopped waiting
      When the original control promise rejects or returns a negative outcome
      Then its bounded diagnostic is recorded on the still-current pinned incarnation
      And inspect exposes that failure without a guessed idle restoration or new input
      And the diagnostic never writes to a same-name successor

    Scenario: A rejected late operation is observed without an unhandled rejection
      Given a cancelled tool wait
      When its pending operation rejects
      Then the rejection is consumed and recorded on its still-current exact incarnation
      And it never changes or reaches a successor
