Feature: Explicit bounded child-to-parent intermediate messages

  The child may contribute only when the surface explicitly grants the
  agent_message capability. Its successful tool result reports emitted text;
  the parent owns exact incarnation/input routing and final settlement.

  Scenario: A successful agent_message result reaches the parent as one notice
    Given an explicitly granted child emits one successful agent_message result
    When the resident RPC stream contains the tool_execution_end event
    Then the parent callback receives one bounded payload in sequence order
    And no final response or settlement state is changed

  Scenario: Invalid or failed tool results are ignored
    Given the child emits blank, unknown, oversized, and failed agent_message results
    When the resident parses tool_execution_end events
    Then no invalid payload reaches the parent callback

  Scenario: A replaced child cannot deliver a late parent message
    Given an old incarnation is replaced by a same-name child
    When the old child emits a late successful agent_message result
    Then the replacement receives no message from the old incarnation

  Scenario: A temporary child has no implicit messaging grant
    Given a temporary child starts without agent_message in its tool grant
    When its model attempts an agent_message call
    Then the child has no registered parent-message tool
    And the parent receives no intermediate notice

  Scenario: Intermediate delivery preserves input ownership and bounds
    Given an active input has an explicit parent-message grant
    When duplicate calls or messages exceeding the input quota arrive
    Then duplicate calls are ignored and quota violations retain a bounded diagnostic
    And the child remains working without settling or dispatching queued input

  Scenario: Tool call identifiers have a bounded UTF-8 identity
    Given an active input has an explicit parent-message grant
    When a callback receives exact-bound and oversized ASCII or multibyte tool call identifiers
    Then the exact-bound identifiers may be delivered and oversized identifiers are rejected before dedupe state

  Scenario: A later input can reuse a tool call identifier
    Given a queued input starts after the previous final result in the same session
    When that input emits a previously used tool call identifier
    Then its intermediate notice has the new input identifier and the next sequence
    And a late delivery failure from the earlier input cannot alter the new input

  Scenario: Intermediate and final messages have separate TUI rows
    Given the parent receives intermediate progress followed by a final result
    When their registered renderers produce the transcript
    Then progress uses the message lifecycle and the final result uses its result lifecycle
    And malformed intermediate details render a stable unreadable fallback
