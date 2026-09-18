# Specification: Desk Link Hosted Pi Console

**Status:** ready-for-agent

## Problem Statement

Open DeskOS can show a Mac's Pi sessions on the desk, but nothing runs the other way. A developer sitting at a Mac cannot start work on the desk's own Pi host, cannot see what that work is doing while it runs, and cannot steer or stop it. The desk's Pi host already accepts coding requests and answers with a durable receipt, but a receipt arrives either when a request is accepted or when it is already over: the intervening work is invisible, the request cannot be amended, and the only way to reach the host is from the desk itself or from the desk's own voice path.

Worse, the two machines can only be joined by means that do not fit the job. A filesystem or SSH scan cannot carry a live event stream. The desk's existing cross-host task transport is a batch, polled SSH call in the opposite direction. Opening a second port, or reaching the desk over SSH from the Mac, would add a credential path, a discovery path, and an exposed surface in exchange for a polled approximation of the thing that is actually needed.

The result today is that the desk's Pi host is unreachable from the machine where the developer works, and its progress is unknowable while it matters.

## Solution

The Mac's Pi becomes a **Console**: it drives a **Hosted Pi** running on the desk and watches it work.

From the Mac, `/open-deskos` opens a console listing the Hosted Pi sessions the desk currently hosts, each with its state, goal, project, and age. `Enter` attaches to one; from then on the desk's turns stream into the console surface as they happen, typing a line sends the next instruction into the same session, `x` cancels the running turn, and the final response arrives when the work ends. The session survives the Mac closing its link, and re-attaching by identity replays the retained tail without repeating anything already seen. The desk states who is driving for as long as that control exists, and local touch and keyboard keep working exactly as before.

Control travels on the Desk Link the Mac already opens, authorized by a Control Credential that is separate from the reporting token. A machine that presents only the reporting token stays as report-only as it is today, and an unconfigured machine remains silent. The desk's Desk Link Service brokers control to its own Pi host, so nothing needs to reach the desk from outside the local network, and no second listener is added.

A Hosted Pi has a normal Pi session's capability: it may commit, push, install, deploy, and restart services, and it is driven the same way whether a Console started it or a voice request did.

## User Stories

1. As a Mac developer, I want to see which Hosted Pi sessions the desk is currently hosting, so that I can tell what work exists on it before I interfere.
2. As a Mac developer, I want each listed Hosted Pi to show its state, goal, project, and age, so that I can pick the one I mean without guessing from an identifier.
3. As a Mac developer, I want to press Enter on a listed Hosted Pi to attach to it, so that entering a desk session is one keystroke rather than a command I must compose.
4. As a Mac developer, I want the desk's turn events to stream into my console while they happen, so that I can see progress instead of waiting for a final answer.
5. As a Mac developer, I want to type a line into the console to send the next instruction into the attached Hosted Pi, so that I can redirect the work without restarting it or re-describing the context.
6. As a Mac developer, I want to cancel the turn that is currently running on the desk, so that a wrong direction costs seconds rather than a whole task.
7. As a Mac developer, I want the final response of a Hosted Pi delivered into my session when it ends, so that the result is part of my conversation rather than something I must go and fetch.
8. As a Mac developer, I want to launch a new Hosted Pi on the desk with a prompt and a project, so that work can start on the desk without leaving my Mac.
9. As a Mac developer, I want a launch to return a durable identity immediately, so that a link interruption cannot lose which session I started.
10. As a Mac developer, I want to re-attach to a Hosted Pi by its identity after my Pi restarts, so that resuming a desk session does not depend on the console staying open.
11. As a Mac developer, I want a replayed event stream to never repeat events I have already applied, so that my context does not fill with duplicates after every reconnect.
12. As a Mac developer, I want a Hosted Pi to keep running when my link drops, so that an outage on my side does not discard the desk's work.
13. As a Mac developer, I want to read a Hosted Pi's complete history and complete tool results on demand, so that the bounded live stream never hides the detail I actually need.
14. As a Mac developer, I want only a bounded tail and the terminal result injected into my own session context, so that watching desk work does not consume my context budget.
15. As a Mac developer, I want to end a Hosted Pi explicitly, so that a finished session stops occupying the desk's concurrency slot.
16. As a Mac developer, I want to see why a Hosted Pi failed, was cancelled, or was interrupted by a host restart, so that I can tell a real failure from my own cancellation.
17. As a Mac developer, I want the assistant on my Mac to be able to list, launch, attach, prompt, cancel, and inspect Hosted Pi sessions through tools, so that I can ask for desk work in natural language.
18. As a Mac developer, I want the console surface to own its own keyboard input while it is open, so that opening it never breaks Pi's model selector, history, or dialogs.
19. As a Mac developer, I want no footer status indicator added for remote control, so that the existing command-only diagnostics contract is preserved.
20. As a Mac developer, I want a machine without a Control Credential to remain report-only, so that a leaked reporting token cannot become an execution path on the desk.
21. As a desk operator, I want control to require a credential separate from the reporting token, so that reporting access and execution access are different privileges.
22. As a desk operator, I want each control connection attributed by machine and session identity, so that remote work on the desk is legible after the fact.
23. As a desk operator, I want the desk to state which Console is driving a Hosted Pi for as long as that control exists, so that the desk is never silently driven from another machine.
24. As a desk operator, I want local touch and keyboard to keep working while a Hosted Pi is driven remotely, so that remote control never locks me out of my own desk.
25. As a desk operator, I want Control Attribution to clear when the Console disconnects, so that a stale attribution cannot claim a driver that is gone.
26. As a desk operator, I want a Hosted Pi visible in the desk's existing Pi Sessions surface, so that remote work appears where every other session appears instead of in a new page.
27. As a desk operator, I want a voice-started Hosted Pi to have the same capability as a Console-driven one, so that I do not have to reason about two capability tiers.
28. As a desk operator, I want a Hosted Pi to be able to run any tool the desk's Pi can, so that "remote control" means control rather than a restricted subset.
29. As a desk operator, I want intake rules unchanged — an operator-configured development root, a host-wide concurrency cap, and durable receipts — so that lifting the capability guardrail does not widen admission.
30. As a desk operator, I want an interrupted Hosted Pi not to replay its prompt after a host restart, so that a restart never re-runs work with side effects.
31. As a desk operator, I want a cancelled or failed Hosted Pi to keep its durable receipt, so that the desk records what happened even after the session is gone.
32. As a desk operator, I want one Console to drive one Hosted Pi at a time, so that two machines cannot interleave instructions into the same session without knowing it.
33. As a desk operator, I want a new attach to replace the previous Console rather than share it, so that the driving authority is always exactly one session.
34. As a maintainer, I want an unconfigured or reporting-only machine to behave exactly as it does today, so that the protocol change cannot regress existing reporting.
35. As a maintainer, I want the control records and replies bounded and versioned like the reporting ones, so that a Console cannot flood the desk or force an unbounded read.
36. As a maintainer, I want the two repositories to share one verified wire contract rather than two interpretations of it, so that the Mac client and the desk service cannot drift apart silently.
37. As a maintainer, I want no test to require the desk device or a live model, so that the whole contract is verifiable on a development machine.
38. As a maintainer, I want the ADRs and domain vocabulary to be the source of the terms used in code and tests, so that "Hosted Pi", "Console", "Control Link", "Attach", and "Control Attribution" keep their meanings.

## Scenarios

```gherkin
Feature: Remote control of a desk-hosted Pi from a Mac Console

  Background:
    Given a Desk Link Service accepting links on the local network
    And a Pi host on the same machine with at least one configured development root

  Scenario: A reporting-only link stays report-only
    Given a machine has only the reporting token
    When its Pi session connects and reports
    Then the link authenticates as reporting
    And any control record on that link is refused
    And its Reported Sessions appear exactly as before

  Scenario: An unconfigured machine stays silent
    Given a machine has no Desk Link address, reporting token, or Control Credential
    When its Pi session runs
    Then no connection is attempted
    And no Hosted Pi is listed, launched, or attached

  Scenario: A machine with a Control Credential becomes a Console
    Given a machine presents the reporting token and a valid Control Credential
    When its Pi session connects
    Then the link authenticates for control as well as reporting
    And the Console can list the desk's Hosted Pi sessions

  Scenario: A refused Control Credential does not break reporting
    Given a machine presents a valid reporting token and an invalid Control Credential
    When its Pi session connects
    Then the link authenticates as reporting only
    And the refusal is reported to the Console
    And its Reported Sessions still appear on the desk

  Scenario: The desk lists its Hosted Pi sessions
    Given the desk hosts more than one Hosted Pi session
    When the Console asks for the list
    Then each entry carries a durable identity, state, project, and age
    And a goal is present when the session has one
    And the list is bounded

  Scenario: The desk hosts a new Hosted Pi
    Given the Console names a project inside a configured development root
    When the Console launches a Hosted Pi with a prompt
    Then the desk returns a durable identity before execution starts
    And the Hosted Pi is reported as running while its turn executes
    And the desk's durable receipt exists before the turn starts

  Scenario: A launch outside the configured roots is refused
    Given a project outside every configured development root
    When the Console launches a Hosted Pi for it
    Then the launch is refused
    And no session is created

  Scenario: A launch with an invalid prompt is refused
    Given a prompt that is empty, oversized, or not valid UTF-8
    When the Console launches a Hosted Pi with it
    Then the launch is refused
    And the refusal names the invalid request

  Scenario: A Hosted Pi streams its turn events with an increasing sequence
    Given a Console is attached to a running Hosted Pi
    When the Hosted Pi produces events
    Then each event carries the Hosted Pi identity and a sequence number greater than the previous one for that session
    And the events respect the same bounds as Session Events
    And the Console applies them in sequence order

  Scenario: Re-attaching replays the retained tail without repeating events
    Given a Console has applied events up to a sequence number
    When it attaches again to the same Hosted Pi
    Then the retained tail is delivered again
    And no event with an already applied sequence number is applied twice

  Scenario: A Hosted Pi survives its Console disconnecting
    Given a Hosted Pi is running with an attached Console
    When the Console's link drops
    Then the Hosted Pi keeps its state and its identity
    And it stays attachable by that identity
    And its Control Attribution on the desk clears

  Scenario: An attached Console can steer the running turn
    Given a Console is attached to a Hosted Pi
    When the Console sends a prompt
    Then the prompt is delivered to that same session
    And the Hosted Pi's state and events reflect the delivered turn

  Scenario: A Console can cancel the running turn
    Given a Hosted Pi is executing a turn
    When the Console cancels it
    Then the executing turn is aborted
    And the session keeps its identity and stays attachable
    And the durable receipt records a cancellation rather than a success

  Scenario: A Console can end a Hosted Pi
    Given a Hosted Pi is alive with a durable receipt
    When the Console ends it
    Then the session is disposed
    And its concurrency slot is released
    And its terminal receipt remains readable

  Scenario: A Hosted Pi is idempotent by identity
    Given a launch was accepted with a durable identity
    When an identical launch request arrives with that identity
    Then the existing Hosted Pi is returned
    And a request with that identity but a different prompt, project, or state is refused

  Scenario: A Hosted Pi keeps running after an unknown outcome
    Given a launch or cancel request whose response never arrived
    When the Console reconciles by identity
    Then the desk reports the current state of that identity
    And the Console does not automatically repeat a mutation

  Scenario: Hosted Pi states are distinguishable
    Given a Hosted Pi that is alive and idle at its prompt
    And a Hosted Pi whose host restarted mid-turn
    And a Hosted Pi whose turn failed
    And a Hosted Pi whose turn was cancelled
    When the Console reads their states
    Then the alive-but-idle session is distinguished from a terminal one
    And an interruption caused by a host restart is distinguished from a failure
    And a cancellation is distinguished from a failure

  Scenario: A complete history and complete tool results are readable on demand
    Given a Hosted Pi whose bounded live stream omitted earlier detail
    When the Console asks for its history
    Then the desk answers with the complete session history and complete tool results
    And the answer is bounded per request and paged rather than truncated silently

  Scenario: Only a bounded tail and the terminal result enter the Console's own context
    Given a Console attached to a Hosted Pi that produces more events than the injection bound
    When those events arrive
    Then the driving Pi session receives a bounded tail rather than every event
    And the terminal result is delivered when the Hosted Pi ends
    And the complete content remains available on demand rather than in context

  Scenario: One Console drives a Hosted Pi at a time
    Given a Hosted Pi is attached to one Console
    When another Console attaches to the same Hosted Pi
    Then the newer attach becomes the driver
    And the previous Console is no longer the driver
    And the driving authority is exactly one Console

  Scenario: The desk states its Control Attribution
    Given a Console is attached to a Hosted Pi
    When the desk renders its Pi Sessions surface
    Then that Hosted Pi is present with the driving machine named
    And the attribution stays while the control exists
    And it clears when the Console disconnects

  Scenario: Local input keeps working under remote control
    Given a Console is driving a Hosted Pi
    When a person uses the desk's touch screen or keyboard
    Then local input is handled exactly as it is without remote control
    And remote control never takes local driving authority away

  Scenario: Hosted Pi capability is a normal Pi session's capability
    Given a Hosted Pi with an admitted project
    When its turn requests a commit, a push, an installation, a deployment, or a service restart
    Then the request is not blocked by a capability guardrail
    And the desk's own operational rules for durable receipts still apply

  Scenario: Intake rules are unchanged
    Given the desk's host-wide concurrency limit is reached
    When the Console launches another Hosted Pi
    Then the launch is refused without running another session
    And a Hosted Pi whose project overlaps a running one is refused

  Scenario: A host restart never replays work
    Given a durable receipt for a Hosted Pi that was running
    When the Pi host restarts
    Then that Hosted Pi is marked interrupted
    And its prompt is not replayed

  Scenario: Control is attributed for audit
    Given a Console that launched or drove a Hosted Pi
    When the desk records the Hosted Pi's receipt
    Then the controlling machine and session identity are recorded
    And the record survives a Console disconnect

  Scenario: The console surface owns its own input
    Given the Console surface is open in a Pi session
    When the user presses keys in it
    Then those keys are handled by the surface itself
    And Pi's model selector, history, and dialogs are unaffected

  Scenario: Diagnostics stay command-only
    Given a machine is configured or unconfigured
    When a Console connects, attaches, drops, or reconnects
    Then Open DeskOS never sets or clears a footer status
    And it never installs a custom footer or working-directory suffix
    And control state is available only through the console command and its surface

  Scenario: A bounded control request cannot flood the desk
    Given a Console that sends oversized or malformed control records
    When the service reads them
    Then the oversized record is refused without disconnecting the link
    And the malformed record never breaks the link
    And the service keeps answering valid records

  Scenario: A reporting machine cannot read another machine's Hosted Pi control
    Given two machines with valid reporting tokens and one Control Credential
    When the machine without the Control Credential asks for a Hosted Pi
    Then the request is refused
    And no Hosted Pi state is disclosed to it
```

## Implementation Decisions

1. **One connection, two authorities.** The Desk Link keeps being the single package-initiated connection. Its handshake carries the reporting token and, optionally, the Control Credential. Missing or refused control material degrades to reporting-only; it never fails the reporting link. No second listener, port, or discovery path is added.
2. **Control records on the wire.** Console-to-desk records: list, launch, attach, prompt, cancel, end, history. Desk-to-Console records: snapshot, event, state, acknowledgement, error. Every Hosted Pi event carries the Hosted Pi identity and a per-session monotonic sequence. The protocol version increments; version-1 reporter records and service replies keep working unchanged.
3. **Bounded frames and bodies.** Control records reuse the existing frame, request, and reply bounds, and Session Event content reuses the existing Session Event bounds. A Console may read complete history and complete tool results on demand through the history record, which is bounded per answer and paged rather than truncated silently.
4. **The service becomes a broker.** The Desk Link Service relays control to the desk's Pi host over its existing private Unix socket, and holds the live state the desk renders, including Control Attribution. The runtime keeps reading its own socket; the Control Link never exposes that socket directly.
5. **The Pi host keeps its intake rules and loses its capability guardrail.** Hosted Pi replaces the managed coding task term and semantics. Development-root admission, the durable receipt written before execution, the host-wide concurrency cap, no automatic retry of an unknown mutation, and no prompt replay after a restart all stay. The edit-and-test-only policy is removed from the host's session instructions.
6. **Hosted Pi is a persistent session rather than a one-shot run.** The session survives turns, so the state vocabulary gains a live idle state — "settled", Pi's own word for idle at a prompt — alongside running and the terminal states. Ending a session is an explicit operation that disposes the session and releases its slot while leaving the receipt readable.
7. **One Console, one Hosted Pi.** Attach is by Hosted Pi identity, idempotent, and replacing: the newest attach is the driver and the previous Console stops being it. The Console records its attached identity in its own session so a resumed Pi session can re-attach without the console surface being open.
8. **Separation of fidelity and injection.** The console surface shows everything the desk sends; the complete history is available on demand; what enters the driving session's own context is a bounded tail plus the terminal result, delivered as a follow-up message so it becomes part of the conversation.
9. **Desk presentation reuses existing surfaces.** A Hosted Pi is registered with the desk like any other session and appears in the existing Pi Sessions surface with its Control Attribution. No new page, widget, or state-bar element is introduced, and the existing command-only diagnostics contract stands.
10. **Mac-side surface.** `/open-deskos` opens the console surface with no arguments and takes fast-path arguments for attach, launch, cancel, and history. The assistant-facing tools are snake-cased and prefixed `desk_`, covering list, start, attach, prompt, cancel, status, history, and end. The surface owns its input through Pi's own custom-UI mechanism and never intercepts global terminal input.
11. **Credential provisioning stays out of band.** The Control Credential is provisioned like the reporting token: a private environment file on each side, never in source, a unit file, or a command line.
12. **Vocabulary is fixed.** Hosted Pi, Console, Control Link, Control Credential, Attach, and Control Attribution carry the meanings recorded in the CM5 architecture glossary; the desk's own "Remote" terms keep meaning the ESP32-S3 remote control and are never reused for this capability.

## Testing Decisions

- **One seam: the Desk Link wire contract.** The Console and the service meet at exactly one public boundary, so the contract is verified there and nowhere else. Both sides already have this seam in place.
- **Desk side.** The existing service test drives a real TCP connection against the service while the runtime side answers over a temporary Unix socket; the Pi host is constructed with its already-injected runner adapter so the host's lifecycle, admission, receipts, and event sequence are exercised without a model. Prior art: the desk's Desk Link Service tests and the Pi host's task service and protocol tests.
- **Mac side.** The Console client is constructed with the transport factory the reporter already receives, so the wire records it emits and the records it applies are asserted against a fake desk; the extension-level test runs against a real loopback TCP server, the way the reporter's discovery test already does. Prior art: the Open DeskOS package's existing reporter, multiline-result, and extension tests.
- **What makes a good test here.** Tests assert observable behavior at those boundaries — the records on the wire, the state the desk reports, the events the Console applies, and the bounded content that enters context. They must not assert internal helpers, must not call a model, and must not need the desk device. Scenario-per-behavior: each `.feature` scenario pins one behavior, and its test fails first for the stated reason.
- **Scenario storage.** The desk-side scenarios extend the Pi host's feature file area; the Mac-side scenarios extend the Open DeskOS package's feature file. Both are executed by their repositories' existing runners.
- **Regression order.** The reporting scenarios and the existing event-bound scenarios run unchanged after every control change, because reporting compatibility is the one behavior this work must not disturb.

## Out of Scope

- Deploying to the desk device and restarting its services. Repository work and its tests are in scope; the device write is a separate authorization.
- Taking over arbitrary desk Pi sessions: the resident voice agent's own conversation and sessions a person started in a terminal are not Hosted Pi sessions and are not attachable.
- Many-to-many control: multiple Consoles fanning out to one Hosted Pi, or one Console driving several at once.
- Encrypting or tunneling the Control Link: it stays a plain LAN connection behind a shared secret, and it must never be exposed beyond the local network.
- Any Mac-side capability beyond controlling Hosted Pi sessions: the package still does not manage Reported Sessions, and visibility never makes one controllable.
- Replacing the desk's voice entry point or its personal-agent capabilities.
- Issue-tracker and domain-doc scaffolding for either repository; the local `docs/spec-*.md` and `.scratch/<feature>/issues/` conventions already in use are followed instead.

## Further Notes

- Two accepted ADRs in the desk repository record the load-bearing decisions: control traveling on the Desk Link with a separate credential, and the removal of the edit-and-test-only capability guardrail. The CM5 architecture glossary carries the new terms.
- **Accepted risk:** because the guardrail is removed for the whole capability rather than only for Console-driven sessions, a mis-transcribed voice request can now commit, push, install, deploy, or restart a service. Control Attribution covers Console-driven sessions only, so a voice-started Hosted Pi carries no attribution line. The mitigations considered — an origin-scoped policy, a per-session operator confirmation, or a local confirmation on the desk — are recorded and deliberately not adopted.
- **Compatibility commitment:** with no Control Credential configured, the desk and the package must behave exactly as they do today, including the report-only scenarios and the command-only diagnostics contract. This is the first thing to verify after any protocol change.
- **Device acceptance is separate.** Passing the repository suites shows the contract, not that a real desk installs, restarts, and renders Control Attribution correctly.
- The desk-side tickets for this specification are published in the desk repository's own local issue directory during the tickets step, so each repository carries the work it must do.