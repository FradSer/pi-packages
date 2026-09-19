# Specification: Desk Link Hosted Pi Console

**Status:** rewritten to the simplified design (independent-review corrections included); tickets pending approval

## Problem Statement

Open DeskOS can show a Mac's Pi sessions on the desk, but nothing runs the other way. A developer sitting at a Mac cannot start work on the desk's own Pi host, cannot see what that work is doing while it runs, and cannot steer or stop it. The desk's Pi host already accepts coding requests and answers with a durable receipt, but a receipt arrives either when a request is accepted or when it is already over: the intervening work is invisible, the request cannot be amended, and the only way to reach the host is from the desk itself or from the desk's own voice path.

The two machines can only be joined today by means that do not fit the job. A filesystem or SSH scan cannot carry a live event stream. The desk's existing cross-host task transport is a batch, polled SSH call in the opposite direction. A second port, or reaching the desk over SSH from the Mac, would add a credential path, a discovery path, and an exposed surface in exchange for a polled approximation of the thing that is needed.

So the desk's Pi host is unreachable from the machine where the developer works, and its progress is unknowable while it matters.

## Solution

The Mac's Pi becomes a **Console**: it drives a **Hosted Pi** running on the desk and watches it work.

From the Mac, `/open-deskos` opens a menu whose shape does not change with configuration. The console is one of its entries, and it lists the Hosted Pi sessions the desk hosts, each with its state, goal, project, and age. Entering one attaches to it: the console then shows that session's work, typing a line sends the next instruction into the same session, one key cancels the running turn, another ends the session, and the final response arrives when the work ends. The session survives the Mac closing its connection, and attaching again by identity resumes exactly where it left off: it reads the history up to the boundary it had reached, then continues live from there, so nothing is repeated and nothing is skipped. The desk states who is driving for as long as that control exists, and local touch and keyboard keep working exactly as before.

Control travels over the desk's existing LAN listener, authorized by a Control Credential that is separate from the reporting token and never travels on the wire. A machine that presents only the reporting token stays as report-only as it is today, and an unconfigured machine remains silent. The desk's Desk Link Service gains a path to its own Pi host, which it does not have today. The desk therefore never has to reach the Mac, and no second listener is added.

A Hosted Pi may commit, push, install, deploy, and restart services within the tool set the desk's Pi host exposes, and it is driven the same way whether a Console started it or a voice request did. The host loads no extensions, skills, or prompt templates, so this is the host's tool set rather than everything a full Pi installation could do.

## User Stories

1. As a Mac developer, I want to see which Hosted Pi sessions the desk is currently hosting, so that I can tell what work exists on it before I interfere.
2. As a Mac developer, I want each listed session to show its state, goal, project, and age, so that I can pick the one I mean without guessing from an identifier.
3. As a Mac developer, I want entering a listed session to be one keystroke, so that attaching is not a command I must compose.
4. As a Mac developer, I want the desk's turn events to reach me while they happen, so that I can see progress instead of waiting for a final answer.
5. As a Mac developer, I want to type a line into the console to send the next instruction into the attached session, so that I can redirect the work without restarting it or re-describing the context.
6. As a Mac developer, I want to cancel the turn that is currently running, so that a wrong direction costs seconds rather than a whole task.
7. As a Mac developer, I want to end a session explicitly, so that a finished session stops occupying the desk's concurrency slot.
8. As a Mac developer, I want the final response delivered into my own session when a Hosted Pi ends, so that the result is part of my conversation rather than something I must go and fetch.
9. As a Mac developer, I want to launch a new Hosted Pi with a prompt and a project, so that work can start on the desk without leaving my Mac.
10. As a Mac developer, I want a launch to return a durable identity immediately, so that a lost connection cannot lose which session I started.
11. As a Mac developer, I want to re-attach by identity after my Pi restarts, so that resuming does not depend on the console staying open.
12. As a Mac developer, I want re-attaching to continue exactly where I left off, so that I neither re-read work I already saw nor silently lose what happened while I was away.
13. As a Mac developer, I want a Hosted Pi to keep running when my connection drops, so that an outage on my side does not discard the desk's work.
14. As a Mac developer, I want to read a session's complete history and complete tool results on demand, so that the live view never hides the detail I actually need.
15. As a Mac developer, I want only a bounded tail and the terminal result injected into my own session context, so that watching desk work does not consume my context budget.
16. As a Mac developer, I want to see why a session failed, was cancelled, or was interrupted by a host restart, so that I can tell a real failure from my own cancellation.
17. As a Mac developer, I want the assistant on my Mac to be able to list, launch, attach, prompt, cancel, end, and read history through tools, so that I can ask for desk work in natural language.
18. As a Mac developer, I want the console surface to own its own keyboard input while open, so that opening it never breaks Pi's model selector, history, or dialogs.
19. As a Mac developer, I want no footer status indicator added for Hosted Pi control, so that the existing command-only diagnostics contract is preserved.
20. As a Mac developer, I want a machine without a Control Credential to remain report-only, so that a leaked reporting token cannot become an execution path on the desk.
21. As a Mac developer, I want the control credential to never be transmitted, so that watching the network cannot yield a reusable way to run commands on the desk.
22. As a desk operator, I want the desk to state which Console is driving a Hosted Pi for as long as that control exists, so that the desk is never silently driven from another machine.
23. As a desk operator, I want local touch and keyboard to keep working while a session is driven remotely, so that control never locks me out of my own desk.
24. As a desk operator, I want a Hosted Pi visible where every other session is visible, so that remote work does not live on a private page.
25. As a desk operator, I want a Hosted Pi never to be presented as a report-only session, so that inspecting a session and controlling it stay different things.
26. As a desk operator, I want each control connection attributed by machine and session identity, so that remote work on the desk is legible afterwards.
27. As a desk operator, I want a voice-started Hosted Pi to have the same capability as a Console-driven one, so that I do not have to reason about two capability tiers.
28. As a desk operator, I want a Hosted Pi to run every tool the desk's Pi host exposes, so that control means control rather than a restricted subset.
29. As a desk operator, I want intake rules to stay as they are, with a configured development root, a host-wide cap, and durable receipts, so that lifting the capability guardrail does not widen admission.
30. As a desk operator, I want an idle, unattached session to stop blocking its project, so that a session left open does not prevent work elsewhere in the same project.
31. As a desk operator, I want an abandoned session to expire, so that forgotten sessions cannot permanently consume the desk's capacity.
32. As a desk operator, I want an interrupted Hosted Pi not to replay its prompt after a host restart, so that a restart never re-runs work with side effects.
33. As a desk operator, I want a cancelled or failed session to keep its durable receipt, so that the desk records what happened even after the session is gone.
34. As a desk operator, I want one Console to drive a session at a time, so that two machines cannot interleave instructions without knowing it.
35. As a maintainer, I want an unconfigured or reporting-only machine to behave exactly as it does today, so that the protocol change cannot regress existing reporting.
36. As a maintainer, I want one coordinate for both live events and history, so that the two can never disagree about what a Console has already seen.
37. As a maintainer, I want no separate event replay buffer or counter to maintain, so that the desk holds no state that its own session log already holds durably.
38. As a maintainer, I want an explicit version mismatch to be refused, so that a newer Console does not look like a credential failure and reconnect forever.
39. As a maintainer, I want the two repositories to share one verified wire contract rather than two interpretations of it, so that the Mac client and the desk service cannot drift apart silently.
40. As a maintainer, I want no test to require the desk device or a live model, so that the whole contract is verifiable on a development machine.
41. As a maintainer, I want the ADRs and domain vocabulary to be the source of the terms used in code and tests, so that Hosted Pi, Console, Control Link, Control Credential, Attach, and Control Attribution keep their meanings.

## Scenarios

```gherkin
Feature: Hosted Pi control from a Mac Console

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
    Given a machine presents the reporting token and proves the Control Credential
    When its control connection opens
    Then the link authenticates for control as well as reporting
    And the Console can list the desk's Hosted Pi sessions

  Scenario: The control credential is never transmitted
    Given a machine opens a control connection
    When the desk challenges it with a one-time nonce
    Then the machine answers with a proof over that nonce
    And the credential itself never appears on the wire
    And a replayed captured proof does not authenticate

  Scenario: A refused Control Credential does not break reporting
    Given a machine presents a valid reporting token and cannot prove a valid Control Credential
    When its Pi session connects
    Then the link authenticates as reporting only
    And the refusal is reported to the Console
    And its Reported Sessions still appear on the desk

  Scenario: A version mismatch is refused explicitly
    Given a Console speaking a protocol version the desk does not accept
    When it connects
    Then the desk refuses the connection and names the mismatch
    And the Console does not retry as though the credential had failed

  Scenario: Two Pi sessions on one machine are distinguishable Consoles
    Given two Pi sessions on one machine both hold the Control Credential
    When they connect
    Then each is identified by its session identity and machine name
    And the desk does not merge them into one Console

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

  Scenario: A Hosted Pi is idempotent by identity
    Given a launch was accepted with a durable identity
    When an identical launch request arrives with that identity
    Then the existing Hosted Pi is returned
    And a request with that identity but a different prompt or project is refused

  Scenario: Live events carry the session log's own ordering
    Given a Console is attached to a running Hosted Pi
    When the Hosted Pi appends entries to its session log
    Then each event carries that entry's position in the log
    And positions increase for that session and never restart after a host restart
    And the events respect the same bounds as Session Events

  Scenario: Attaching continues from a boundary instead of replaying a window
    Given a Console previously applied events up to a position
    When it attaches again to the same Hosted Pi
    Then it reads history from that position to the current boundary
    And it consumes live events only from that boundary onward
    And no event position is applied twice and none is skipped

  Scenario: A first attach begins at the current boundary
    Given a Hosted Pi that has been running with no Console attached
    When a Console attaches for the first time
    Then it learns the current boundary before consuming live events
    And a history read is what shows it what already happened
    And the desk does not retain a replay window for it

  Scenario: A Hosted Pi survives its Console disconnecting
    Given a Hosted Pi is running with an attached Console
    When the Console's connection drops
    Then the Hosted Pi keeps its state and its identity
    And it stays attachable by that identity
    And its Control Attribution on the desk clears

  Scenario: An attached Console can steer the running turn
    Given a Console is attached to a Hosted Pi
    When the Console sends a prompt while a turn is executing
    Then the prompt steers that same turn rather than starting a second one
    And the Hosted Pi's state and events reflect the delivered instruction

  Scenario: A Console can cancel the running turn
    Given a Hosted Pi is executing a turn
    When the Console cancels it
    Then the executing turn is aborted
    And the session is not disposed, keeps its identity, and stays attachable
    And the durable receipt records a cancellation rather than a success

  Scenario: A Console can end a Hosted Pi
    Given a Hosted Pi is alive with a durable receipt
    When the Console ends it
    Then the session is disposed
    And its concurrency slot is released
    And its terminal receipt remains readable

  Scenario: One Console drives a Hosted Pi at a time
    Given a Hosted Pi is attached to one Console
    When another Console attaches to the same Hosted Pi
    Then the newer attach becomes the driver
    And the previous Console is no longer the driver
    And the driving authority is exactly one Console

  Scenario: An idle unattached session stops blocking its project
    Given a Hosted Pi that is alive, idle, and attached to no Console
    When a launch requests an overlapping project
    Then the launch is admitted when the host-wide cap allows it
    And the idle session does not hold the project's overlap lock

  Scenario: An abandoned session does not consume the desk forever
    Given a Hosted Pi that has been idle and unattached beyond the idle bound
    When the bound passes
    Then the session is released without replaying its prompt
    And an operator can also end it explicitly before that

  Scenario: Hosted Pi states are distinguishable
    Given a Hosted Pi that is alive and idle at its prompt
    And a Hosted Pi whose host restarted mid-turn
    And a Hosted Pi whose turn failed
    And a Hosted Pi whose turn was cancelled
    When the Console reads their states
    Then the alive-but-idle session is distinguished from a terminal one
    And an interruption caused by a host restart is distinguished from a failure
    And a cancellation is distinguished from a failure
    And no state is reported as running when it is unknown

  Scenario: A complete history and complete tool results are readable on demand
    Given a Hosted Pi whose live view omitted earlier detail
    When the Console asks for its history from a position
    Then the desk answers from the session's own log, paged and bounded
    And reaching a bound yields an explicit continuation rather than a shortened answer presented as complete

  Scenario: Only a bounded tail and the terminal result enter the Console's own context
    Given a Console attached to a Hosted Pi that produces more events than the injection bound
    When those events arrive
    Then the driving Pi session receives a bounded tail rather than every event
    And the terminal result is delivered when the Hosted Pi ends
    And the complete content stays available on demand rather than in context

  Scenario: The desk states its Control Attribution
    Given a Console is attached to a Hosted Pi
    When the desk renders its Pi Sessions surface
    Then that Hosted Pi is present and the driving machine is named
    And the Hosted Pi is distinguishable from a report-only session
    And the attribution stays while the control exists
    And it clears when the Console disconnects

  Scenario: Local input keeps working under Hosted Pi control
    Given a Console is driving a Hosted Pi
    When a person uses the desk's touch screen or keyboard
    Then local input is handled exactly as it is without a Console attached
    And a Console never takes local driving authority away

  Scenario: Hosted Pi capability is the host's tool set
    Given a Hosted Pi with an admitted project
    When its turn requests a commit, a push, an installation, a deployment, or a service restart
    Then the request is not blocked by a capability guardrail
    And the host's durable-receipt and no-replay rules still apply

  Scenario: Intake rules are unchanged apart from slot ownership
    Given the desk's host-wide concurrency limit is reached
    When the Console launches another Hosted Pi
    Then the launch is refused without running another session

  Scenario: A host restart never replays work
    Given a durable receipt for a Hosted Pi that was running
    When the Pi host restarts
    Then that Hosted Pi is marked interrupted
    And its prompt is not replayed
    And a later attach can still read what its log already recorded

  Scenario: Control is attributed for audit
    Given a Console that launched or drove a Hosted Pi
    When the desk records the Hosted Pi's receipt
    Then the controlling machine and session identity are recorded
    And the record survives a Console disconnect

  Scenario: The Pi host being unavailable is answered, not hung
    Given the desk's Pi host is down or its socket is stale
    When a Console asks for the list or launches a session
    Then the desk answers with an explicit failure naming the reason
    And the connection is not left waiting

  Scenario: A desk service restart does not end live sessions
    Given a Hosted Pi is running
    When the Desk Link Service restarts
    Then the Hosted Pi keeps running and keeps its identity
    And a reconnecting Console can attach again and read what it missed from history

  Scenario: The command opens the same menu in every configuration
    Given a machine that is unconfigured, a machine that is report-only, and a machine that is a configured Console
    When the user runs the open-deskos command with no arguments in each case
    Then the same menu opens and lists the same rows
    And a row that is unavailable names the reason rather than disappearing
    And the menu is reachable in all three configurations

  Scenario: The console surface owns its own input
    Given the console surface is open in a Pi session
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
```

## Implementation Decisions

1. **One listener, two connections, two authorities.** The desk keeps its single LAN listener. A machine opens its reporting connection exactly as it does today, and, when it holds a Control Credential, a separate control connection. The reporting connection is untouched: it is fire-and-forget, it resets its backoff on `ack`, and it has no request/reply correlation, so multiplexing control into it would merge two lifecycles into one failure domain.
2. **The control connection is short-lived or attachment-scoped.** A list, launch, or history request uses a one-shot connection. A held connection exists only while a Console is attached, so it is also what Control Attribution's lifetime follows: there is no long-lived idle control connection to keep alive, and no idle reconnect state to reason about.
3. **Handshake.** The control connection carries the protocol version, the reporting token, and a Console identity: the driving Pi session's identity plus its machine name. Two Pi sessions on one machine are therefore distinguishable Consoles. The desk challenges with a one-time nonce; the Console proves possession of the Control Credential with an HMAC over it, and every control record is refused without that proof. The credential itself never travels, so a passive capture yields no reusable execution token. A missing or refused credential degrades the connection to report-only and never affects reporting.
4. **Version negotiation.** The desk accepts a defined window of protocol versions and refuses anything outside it with an explicit reply naming the mismatch. Today the service silently discards any record whose version is not 1, which makes a newer Console look like a credential failure and reconnect forever.
5. **Control records.** Console to desk: list, launch, attach, prompt, cancel, end, and history. Desk to Console: state, event, acknowledgement, and error. There is no detach record: disconnecting, or attaching elsewhere, is what detaching means. Control records reuse the existing frame, request, and reply bounds, and event content reuses the existing Session Event bounds.
6. **One coordinate for live events and history.** A Hosted Pi event's sequence is the position of the corresponding entry in that session's own Pi session log, which the host already writes durably. Positions therefore survive a host restart without a separate counter, a reset rule, or a persisted sequence store, and history and live events are addressed in the same space. This holds because a Hosted Pi is driven linearly; if branching were ever exposed, the coordinate would need revisiting.
7. **No replay window.** On attach, a Console states the position it last applied, or learns the current boundary on a first attach, reads history from that position, and then consumes live events from that boundary onward. Nothing earlier is replayed from memory, so the desk keeps no per-session replay buffer, needs no window sizing or expiry rule, and the silent-gap failure has no way to occur. This follows the closest precedent: the comparable coding-agent server streams live events without a resume cursor and serves catch-up from an explicit position query.
8. **The Pi host is rewritten, not reused.** Today it creates, runs, and disposes a session per request, holds no session across turns, and pushes no events. A persistent session, an event subscription, a second prompt, and a slot that lives past one turn are new work. Admission, the durable receipt written before execution, the host-wide cap, the no-automatic-retry rule, and the no-replay-after-restart rule carry over.
9. **States.** A Hosted Pi is `pending`, `running`, `settled` (alive, idle at its prompt), or terminal as `finished`, `failed`, `cancelled`, or `interrupted`. Steering uses the SDK's own queue semantics: a prompt carries a streaming behavior that is required while a turn streams and ignored when idle. A mid-turn instruction therefore steers the running turn instead of starting a second one. Cancelling aborts the running turn and settles without disposing the session, because disposal is a separate terminal call; ending disposes the session and releases its slot while the receipt stays readable.
10. **Slot ownership.** A live Hosted Pi holds a slot. The overlap rule exists so two sessions cannot edit one project at once, and an idle unattached session is not editing, so it releases the project's overlap lock while still counting against the host-wide cap, and re-acquires the lock when it resumes. A session idle and unattached beyond a bounded period is released without replaying its prompt, and an operator can end it earlier. Four abandoned sessions must never be able to block all further work.
11. **Streaming granularity.** Wire events are built from complete SDK messages mapped onto the existing Session Event bounds. Deltas exist in the SDK and serve the console surface's own liveness locally; they do not go on the wire, and tool partials are not streamed.
12. **Where complete history lives.** A Hosted Pi's history is its own Pi session log under the host's session directory. This work adds no archive. Reads are paged and bounded per request, they use the same coordinate as the live stream, and reaching a bound yields an explicit continuation rather than a shortened answer presented as complete. The durable receipt's bounded response is not a history source.
13. **Separation of fidelity and injection.** The console surface shows what the desk sends and can page through history; what enters the driving session's own context is a bounded tail plus the terminal result, delivered as a follow-up message so it becomes part of that conversation.
14. **Desk presentation extends existing surfaces.** A Hosted Pi appears in the desk's existing Pi Sessions surface, and that requires real work: the surface and its summary arithmetic accept a fixed set of statuses, and the service coerces an unknown status to running, so the state vocabulary has to be extended in both places or a failed session reads as working or makes the whole snapshot unavailable. That enumeration belongs to the desk's own session vocabulary, which is changing while this is written, so an implementer re-reads it rather than trusting this paragraph. Control provenance is its own field with its own render decision, the overview header, while data-source provenance keeps the locations ADR-0005 already assigns it. Neither appears in the session detail, which states session facts only. A Hosted Pi carries an explicit marker so the surface cannot present it as a report-only session, whose semantics are inspect-only. Attribution names the driving machine and session identity, lives exactly as long as the held control connection, and clears when that connection ends. No new page or state-bar element is introduced, and diagnostics stay command-only.
15. **Mac-side surface, menu first.** `/open-deskos` with no arguments opens a second-level menu whose rows are the same in every configuration: the console, the link diagnostics, and the fast paths. A row that is unavailable names its reason instead of disappearing, so the command never changes shape with configuration and a missing variable is reported where the user looks for it. Arguments are the fast path: `console`, `status`, `attach`, `launch`, `cancel`, and `history`. This keeps a reporting entry reporting, which is what Pi's own commands do (its selection commands open a picker, its reporting command reports), and matches the comparable tools, which give hosted-session control its own verb instead of overloading a reporting entry. The assistant-facing tools are snake-cased, prefixed `desk_`, and cover list, start, attach, prompt, cancel, end, and history; there is no separate status tool because a session's state comes from the list and from its live events, and no detach tool because disconnecting is what detaching means. The Console records its attached identity in its own session so a resumed Pi session can attach again. The surface owns its input through Pi's own custom-UI mechanism and never intercepts global terminal input.
16. **Failure answers name a reason.** A desk service restart must not end live sessions; a Pi host that is down or a stale host socket must produce an explicit failure rather than a wait; a mutation whose outcome never arrived is reconciled by identity and never retried automatically; and a project that is deleted or a development root that changes while a session is alive has defined behavior.
17. **Credential provisioning stays out of band.** Both secrets are provisioned as private environment files on each side, never in source, a unit file, or a command line. The documentation names both variables, states the rotation step, and states that content is plaintext and the link is LAN-only.
18. **Vocabulary is fixed.** Hosted Pi, Console, Control Link, Control Credential, Attach, and Control Attribution carry the meanings recorded in the CM5 architecture glossary. The desk's own Remote terms keep meaning the ESP32-S3 remote control and are never reused for this capability.

## Testing Decisions

- **One seam: the Desk Link control contract.** The Console and the service meet at exactly one public boundary, so the contract is verified there and nowhere else.
- **The desk seam has to be redefined before slicing.** The host's existing injected adapter is a one-shot run that returns text and a stop reason, with no session handle, no subscription, and no steer, so streaming, steering, and a mid-turn cancel cannot be reached through it. The seam becomes a host adapter exposing a session factory, an event subscription, and an abort, faked in tests with the shape the SDK actually provides: a session whose subscription delivers complete messages, deltas, and tool-execution updates, whose prompt accepts a steering behavior while a turn streams, and whose abort settles without disposing.
- **One scenario, one behavior.** Each `.feature` scenario pins a single behavior and its test fails first for the stated reason.
- **Desk side.** The service test drives a real TCP connection against the service while the runtime side answers over a temporary Unix socket, and the host is exercised through the adapter above, so no model runs and the device is not needed.
- **Mac side.** The Console client is constructed with the transport factory the reporter already receives, so the records it emits and applies are asserted against a fake desk; the extension-level test runs against a real loopback TCP server, the way the reporter's discovery test already does.
- **What makes a good test here.** Tests assert observable behavior at those boundaries: the records on the wire, the state the desk reports, the events the Console applies, the position it resumes from, and the bounded content that enters context. They must not assert internal helpers and must not need a model or the desk device.
- **Regression order.** The reporting scenarios and the existing event-bound scenarios run unchanged after every control change, because reporting compatibility is the one behavior this work must not disturb.

## Out of Scope

- Deploying to the desk device and restarting its services. Repository work and its tests are in scope; the device write is a separate authorization.
- Taking over arbitrary desk Pi sessions: the resident voice agent's own conversation and sessions a person started in a terminal are not Hosted Pi sessions and are not attachable.
- Many-to-many control: multiple Consoles fanning out to one Hosted Pi, or one Console driving several at once.
- Encrypting or tunneling the Control Link. Content stays plaintext on a LAN-only link; the credential is kept off the wire, and full transport confidentiality stays the transport's job.
- Answering a request from a Hosted Pi mid-turn. The host's SDK exposes no permission, approval, or ask-user surface, its only answer-seeking surface is extension-mediated, and the host loads no extensions, so nothing can raise such a request. Loading extensions is what would make it real, and that is a separate decision.
- Any Mac-side capability beyond controlling Hosted Pi sessions: the package still does not manage Reported Sessions, and visibility never makes one controllable.
- Replacing the desk's voice entry point or its personal-agent capabilities.
- Issue-tracker and domain-doc scaffolding for either repository; the local `docs/spec-*.md` and `.scratch/<feature>/issues/` conventions already in use are followed instead.

## Further Notes

- Two accepted ADRs in the desk repository record the load-bearing decisions: control traveling on the Desk Link with a separate credential, and the removal of the edit-and-test-only capability guardrail. The CM5 architecture glossary carries the new terms.
- **Two in-flight contract changes are recorded, not absorbed.** Two changes are under way that touch what this specification reuses, and neither is part of the contract this document relies on. First, the reporting package's working tree carries an uncommitted change that raises the Session Event bounds to 300 events per session, 1,048,576 bytes, and a per-kind body limit instead of single-line summaries for non-result events, and five of that package's tests still assert the committed contract, so the change is mid-flight rather than landed. This specification deliberately reuses "the existing Session Event bounds" without restating numbers, so it holds either way; the numbers themselves appear in the reporting package's README and in the desk's Desk Link document, and both follow the committed contract until that change lands with its tests. The desk's Desk Link Service enforces the committed bounds itself, because a reporting machine is never trusted to have bounded its own data, so the two sides must be raised together: a reporter sending the larger numbers alone would be trimmed on the desk. Second, the desk's own session vocabulary is being reworked in its working tree (its session filter now reads Live, Working, Idle, Exited), which is the vocabulary the control-provenance and state work has to extend; an implementer re-reads that vocabulary rather than trusting any enumeration written here.
- **Accepted risk:** the guardrail is removed for the whole capability rather than only for Console-driven sessions, so a mis-transcribed voice request can now commit, push, install, deploy, or restart a service. The prohibitions were system-prompt instructions over an unrestricted tool set, so what changed is the likelihood of a mutation, not the ability to make one. Control Attribution covers Console-driven sessions only, so a voice-started Hosted Pi carries no attribution line. The mitigations considered are recorded and deliberately not adopted: an origin-scoped policy, a per-session operator confirmation, or a local confirmation on the desk.
- **Decisions recorded as reversals or defaults.** The entry-command shape was settled by the operator rather than by a default: one command whose no-argument form always opens the same second-level menu, with arguments as the fast path and no footer status in any configuration. It supersedes the earlier proposal that the no-argument form should branch on whether a control credential is configured. Removing the capability guardrail reversed an earlier answer in the same session that chose to keep it; that reversal and its discarded rationale are recorded in the desk repository's guardrail ADR rather than presented as a single coherent decision.
- **Simplifications applied after the review.** A replay window, an explicit resync record, a detach record, a status tool, a separate persisted sequence counter, and a second and third provenance render slot were all removed. Each removal deleted a mechanism rather than a capability; the boundary rule replaced the window, the session log replaced the counter, and one provenance slot replaced three.
- **Prior art consulted.** Happy and Omnara established the shape of remote agent control (list machines, spawn a session, send messages, read history, stop). Coder's agentapi established the small control surface (messages, message, status, events) and streaming events. opencode's server established both the closest architecture (a long-lived server owning sessions, clients that attach, live events plus explicit catch-up by position) and the catch-up rule this specification adopts. Codex's app server established the initialize handshake, capability negotiation, and authentication before any request. tmux and abduco established attach semantics, including detaching other clients and read-only observation. The SSE literature established monotonic ids, bounding a replay window, and never silently resuming from "now"; that failure class cannot occur here, because there is no window to expire.
- **Compatibility commitment:** with no Control Credential configured, the desk and the package must behave exactly as they do today, including the report-only scenarios and the command-only diagnostics contract. This is the first thing to verify after any protocol change.
- **Device acceptance is separate.** Passing the repository suites shows the contract, not that a real desk installs, restarts, and renders Control Attribution correctly.
- The tickets for this specification are published in this repository's local issue directory, one ticket per vertical slice, each naming both the desk-side and the Mac-side halves, because a slice that cuts only one repository is not verifiable end to end. The desk repository carries the glossary and the ADRs.