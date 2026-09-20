Feature: Preserve complete bounded Pi result Markdown over Desk Link

  Scenario: A finalized tool result retains all text blocks
    Given a tool result contains a Markdown table and a fenced code block in separate text parts
    And it contains non-text parts and tool metadata
    When the reporter extracts and sends the result
    Then one result event joins all text parts with two newlines without changing their whitespace
    And the table and code are complete, with no tool prefix in their body
    And the bounded tool name is a separate optional field
    And non-text parts and arbitrary metadata are not reported

  Scenario: Only oversized results have a truncation marker
    Given a result body is at or beyond the 65,536-byte UTF-8 limit
    When it is extracted or recorded directly
    Then the body is preserved up to 65,536 bytes without splitting a Unicode code point
    And only a shortened body has truncated true
    And a previously supplied truncated true remains true
    And user, thinking, tool and assistant events preserve multiline bodies within their per-kind byte bounds

  Scenario: Retained history and offline pending events share bounded tails
    Given a session has emitted results and ordinary events while offline
    When their text and tool-name bytes exceed 1,048,576 bytes or their count exceeds 300
    Then only the newest contiguous event tail fitting both limits is retained
    And pending events obey both limits too
    And tool-name bytes count toward the retained-byte limit
    And result Markdown does not become an unbounded session activity summary

  Scenario: Escaped JSON is split into bounded append-only event frames
    Given retained result bodies contain control characters that expand when JSON encoded
    When the link sends the retained events
    Then every event frame including its final LF is at most 1 MiB
    And frames split only between whole events, preserving their order and content
    And no event is duplicated within that connection
    And sessions snapshots retain their separate 65,536-byte producer budget

  Scenario: Reconnection restores a lost receiver's retained history
    Given a connected reporter has already sent multiline results
    And the service drops the link and may lose all machine event state
    When the reporter reconnects with or without new offline events
    Then it sends the current sessions and all bounded retained events once on that connection
    And later ordinary flushes send only new events
    And the version 1 append-only contract does not promise deduplication if another link kept receiver state alive
