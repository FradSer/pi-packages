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
    Then idle delivery is accepted and busy delivery is queued as followUp
    And neither result claims the agent completed the request
  Scenario: Reject stale targets and replay conflicts
    Given a request was accepted by a live session
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
