Feature: Control only live Pi sessions through private sockets
  Scenario: Reject non-string command values without coercion
    Given a versioned request with an array or object command
    When the request crosses the protocol boundary
    Then validation rejects the command before constructing a request
  Scenario: Deliver through the real SDK without provider credentials
    Given an isolated SDK session with a deterministic input handler
    When the pi-utils live-session client sends a literal prompt to its socket
    Then the SDK receives that exact extension-sourced input once
    And replay returns a receipt without another input event
  Scenario: Discover and submit without claiming completion
    Given a live idle session and a live busy session
    When a client lists sessions and sends text to each exact session ID
    Then idle delivery is handed over and busy delivery is queued as followUp
    And neither result claims the agent completed the request
  Scenario: Reject stale targets and replay conflicts
    Given a request was handed over by a live session
    When the identical requestId and payload are replayed
    Then the original receipt is returned without a second delivery
    When the requestId is reused with different text
    Then the request is rejected
    When the live session closes or switches
    Then its old target cannot receive further messages
  Scenario: Bound and protect the transport
    Given a private directory containing live and stale socket entries
    When clients send malformed or oversized input or use an unsafe directory
    Then requests fail without delivering messages
    And stale entries are not advertised or removed by clients

  Scenario: The live-sessions command is the capability entry point
    Given a live session is reachable through its private socket
    When the user runs /live-sessions
    Then live instances are listed with their state, pid, and sanitized name
    And live instance ids are offered as argument completions
    And when no live session exists the user is told so

  Scenario: Delivery through the command never claims completion
    Given an idle live session and a busy live session
    When the user runs /live-sessions <id> <text> for each
    Then the idle delivery is reported as handed over and the busy one as queued
    And the report states that delivery is not confirmed and completion is not claimed
    And an optional steer prefix requests steering instead of a follow-up

  Scenario: Only the target can confirm a delivery
    Given a live session received text with a requestId
    When it starts a turn whose prompt is exactly that text
    Then a status query for that requestId reports it as confirmed
    And a text it never saw stays unconfirmed
    When the user runs /live-sessions <id> <text> and the target starts that turn
    Then the report says the delivery was confirmed, without claiming completion

  Scenario: Command arguments are bounded before the transport
    Given a delivery with no text, an over-long text, or an over-long session id
    When the user runs /live-sessions with those arguments
    Then the request is refused without reaching any socket

  Scenario: A broken control directory is reported, never shown as empty
    Given the control directory is unusable or a session cannot open its socket
    When the user runs /live-sessions or a session starts
    Then the discovery or startup failure is reported with its cause
    And an unusable directory is not reported as "no live sessions"

  Scenario: A startup failure is remembered by the next listing
    Given a valid control directory whose socket path is too long for this session
    When the session starts and the user then runs /live-sessions
    Then the listing reports that live control is unavailable in this session
    And it does not report that no live sessions exist
