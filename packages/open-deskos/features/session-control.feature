Feature: Let a desk's voice agent drive the session this process is

  Scenario: The endpoint exists only while the session runs
    Given a machine that already reports this Pi session to a desk
    When the session starts and later shuts down
    Then the desk's voice agent can list, read, prompt and cancel that session over the user's own SSH session
    And the endpoint is gone once the session stops
    And no process was installed, no second credential was created, and nothing listens on the network

  Scenario: Nothing is bound before the session starts
    Given the extension is loaded but its session has not started
    When the desk looks for the endpoint
    Then no socket and no descriptor exist
    And the socket only appears from session_start to session_shutdown

  Scenario: The endpoint is private to the user who owns it
    Given a session is bound to its endpoint
    When the endpoint is published
    Then the parent directory is created 0700 and the socket is created 0600
    And the descriptor naming it is written 0600 beside it
    And ownership of the file is the only gate: there is no token to present and no remote listener

  Scenario: The desk sees this session and no other
    Given a bound session
    When the desk lists or reads it
    Then it is answered with this one session, its project, its identity and its latest activity
    And its state is the state the reporter already shows this desk
    And no second process, session store or task record is invented

  Scenario: A project scope is a scope
    Given a bound session working in one project
    When the desk names that project or its parent development root
    Then the session is listed
    And any other project is refused with the protocol's own reason

  Scenario: A prompt becomes a real user message
    Given a bound session
    When the desk sends an instruction
    Then it is delivered as a real user message that triggers a turn
    And a streaming behavior of steer or followUp is delivered as that behavior
    And an omitted behavior uses steer as native Enter does
    And the answer states the state right after delivery
    And an empty, malformed, or foreign-task prompt is refused before anything is delivered

  Scenario: A cancel stops the running turn
    Given a bound session
    When the desk cancels it
    Then Pi's own abort is called and the resulting state is answered

  Scenario: State is observed, never invented
    Given a bound session
    When a turn starts, a message ends, and the agent settles
    Then the state follows those same events the reporter uses
    And the most recent assistant text is the response
    And a turn outcome is reported only once it has been observed, and stays absent until then

  Scenario: A session cannot host sessions
    Given a bound session
    When the desk asks it to start, launch, end, or read Hosted Pi history
    Then every one of them is refused with one fixed reason that this endpoint is a session, not a session host

  Scenario: The protocol is the one the desk already speaks
    Given a bound session
    When a desk opens a connection
    Then one bounded JSON line in is answered by one correlated frame carrying the same request identity
    And a frame, a line, or a request over the protocol's own bounds is refused
    And a connection that sends no line is closed without a frame

  Scenario: A reload replaces the endpoint instead of stacking one
    Given a bound session
    When Pi reloads and the session starts again
    Then the previous endpoint is closed, the descriptor still names the socket, and only one host answers

  Scenario: The desk relays one frame over SSH
    Given a bound session
    When the desk runs the one-shot client on the far side of its own SSH session
    Then the request frame is written to the socket and the reply frame is printed
    And nothing else is printed, the request is never logged, and a transport failure exits non-zero

  Scenario: A machine that declares no endpoint has none to reach
    Given a machine that runs this package without declaring a session endpoint
    When its Pi sessions start
    Then no socket and no descriptor are created
    And the package's reporting is unchanged
    And an endpoint that lets something else hand this session work is a declared capability, never a default

  Scenario: Every session on a machine answers at its own endpoint
    Given a machine with two Pi sessions in two projects
    When both sessions run
    Then each publishes its own descriptor and its own socket
    And neither session is refused for an endpoint the other one already holds
    And a desk resolves the session a project belongs to rather than whichever bound first

  Scenario: The desk finds the session without naming a socket
    Given a desk that declares one executable and sends one request frame
    When the frame names a project
    Then the launcher runs on the far side of the desk's own SSH session and finds the session that owns that project
    And a project no session serves is answered with the protocol's own refusal rather than with another session's reply

  Scenario: The desk's launcher does not assume the login shell's PATH
    Given a machine where node is a version manager's install rather than a system command
    When a desk runs the launcher from a non-interactive SSH session
    Then the launcher finds a node runtime itself and relays the one frame
    And an operator can name the runtime outright

  Scenario: Failed or replaced console connections release their resources
    Given a console connection whose attach fails or whose request cannot be written
    When the request fails or a newer attach replaces it
    Then the connection closes and its pending requests settle exactly once
    And stale records cannot update the current session

  Scenario: Discovery addresses the requested session identity
    Given two local sessions in the same project
    When session-control finds an endpoint for a request with a task ID
    Then it addresses that task's descriptor rather than the first session in the directory

  Scenario: Windows refuses a local endpoint without a verified private IPC gate
    Given a Windows Pi process
    When local session hosting starts
    Then it reports that Windows session hosting is unsupported
    And it publishes no endpoint with weaker access control

  Scenario: A fragmented one-shot request runs once
    Given one connection has submitted a prompt
    When the same connection supplies another fragment
    Then the original prompt is dispatched only once

  Scenario: A development root lists all native sessions below it
    Given two live native sessions in different projects below a development root
    And an obsolete descriptor exists beside their descriptors
    When the relay lists that development root
    Then both live sessions are returned with their exact projects and identities
    And the obsolete descriptor does not hide a live session

  Scenario: Native mutations require the selected session identity
    Given two native sessions in the same project
    When an identity request omits its task ID or names another project
    Then it is refused before any prompt or abort is sent

  Scenario: Native mutation receipts prevent repeat delivery
    Given a native prompt has a mutation ID
    When the same mutation is requested again through another connection
    Then the original receipt is returned without another delivery
    And a changed payload with that mutation ID is refused

  Scenario: Native submission has no identity-aware admission acknowledgment
    Given a native session already has a pending message
    When another instruction is offered
    Then the receipt reports delivery as unknown and forbids an automatic retry
    And status records the instruction as submitted with unknown admission
    When its matching user message is observed
    Then admission remains unknown because manual input can have identical text
    And session prompt and response remain separate execution evidence
    And every submitted mutation ID remains available without replay

  Scenario: Identical queued instructions do not certify each other
    Given a follow-up and a steering instruction contain identical text
    When Pi consumes the steering instruction first
    Then neither mutation is certified from the observed text

  Scenario: A dropped inventory reply cannot prove an empty machine
    Given a native endpoint answers status but closes its list connection without a reply
    When the relay lists the configured development root
    Then the inventory reports incomplete coverage and one unavailable endpoint
    And it does not claim a complete empty inventory

  Scenario: Inventory metadata and newline fit the response bound
    Given a session summary fills the aggregate response budget
    When the relay adds complete inventory metadata and a newline
    Then the entire response remains within the byte limit
    And an oversized summary is omitted with truncated and incomplete set

  Scenario: An operator restricts relay requests to approved project roots
    Given the relay has fixed allow-root arguments
    When a valid request selects a project inside an approved root
    Then it reaches the selected endpoint with its original project string
    When a request selects an outside project, a broad ancestor, or a symlink escape
    Then a fixed correlated refusal is returned before any socket contact
    And malformed or unsupported requests never reach an endpoint
    And the relay ignores SSH_ORIGINAL_COMMAND

  Scenario: The filesystem root admits its descendants
    Given the operator explicitly configures allow-root as the filesystem root
    When a request selects a controlled project directory below that root
    Then the root check admits the project without adding a second separator

  Scenario: Completed console mutations retain their original session ownership
    Given a console mutation for one Hosted Pi awaits its acknowledged completion
    When the console reloads and attaches to another Hosted Pi before the continuation runs
    Then the mutation result names the original Hosted Pi
    And the old continuation neither closes the new attachment nor injects its terminal context
