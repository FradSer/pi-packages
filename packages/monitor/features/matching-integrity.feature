Feature: Bounded complete monitor contracts
  Scenario: Oversized physical lines cannot create anchored sentinels
    Given one physical output line exceeds 64 KiB
    And a fragment suffix would match the success contract on its own
    When the line arrives with or without a newline
    Then the monitor fails with matcher_line_limit
    And the diagnostic tail remains bounded and marked truncated

  Scenario: Line endings do not consume the physical record budget
    Given a physical line contains exactly 64 KiB of payload
    When CR and LF arrive in separate chunks
    Then the line remains eligible for contract matching
    And no matcher_line_limit failure is produced by the delimiter

  Scenario: Named captures have one serialized budget before worker transfer
    Given many named groups capture overlapping output
    When the worker finds a success contract
    Then its response omits positional captures
    And named captures together use at most 32 KiB of serialized JSON
    And capturesTruncated discloses any clipped or omitted capture
    And the original success status is retained

  Scenario: JSON captures receive priority without parsing clipped JSON
    Given a valid json capture and many other named captures
    When all captures cannot fit the total budget
    Then the json capture is retained before other captures
    And the complete json capture still parses correctly
    Given a json capture itself cannot fit the serialized capture budget
    When that capture is clipped or omitted
    Then resultParseError explains the budget failure
    And no parsed result is produced from clipped JSON

  Scenario: An empty JSON capture is an invalid payload
    Given the regex matches a named json group containing an empty string
    When the monitor builds its terminal result
    Then success remains the regex outcome
    And resultParseError reports invalid JSON
