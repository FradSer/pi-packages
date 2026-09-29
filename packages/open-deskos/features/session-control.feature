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
    When the desk names that project or a directory inside it
    Then the session is listed
    And any other project is refused with the protocol's own reason

  Scenario: A prompt becomes a real user message
    Given a bound session
    When the desk sends an instruction
    Then it is delivered as a real user message that triggers a turn
    And a streaming behavior of steer or followUp is delivered as that behavior
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
