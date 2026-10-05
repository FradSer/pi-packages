Feature: Measure monitor cost at the real provider boundary
  Scenario: Private progress is excluded but terminal JSON is accurate
    Given native Pi loads monitor with an isolated offline scripted provider
    When a command emits private progress followed by a JSON terminal sentinel
    Then the provider receives one accurate terminal status and JSON value
    And provider serialization excludes tool details, structuredContent and outputSchema

  Scenario: Compare against the actual bounded bash response
    Given the same native Pi core executes a command with more than 10000 diagnostic lines
    When native bash returns its normal truncated tool response
    Then measurement uses that response rather than the raw subprocess log

  Scenario: Measure repeated execution without inferring polling savings
    Given the same command is actually executed three times in one native session
    When each provider request is serialized with messages and input tool schemas
    Then local tokenizer estimates include fixed guidance, argument, output and cumulative context costs
    And estimates are labeled separately from provider billing and caching

  Scenario: Codemode summary preserves only predeclared required fields
    Given native codemode calls monitor through its normal nested dispatcher
    When its script verifies terminal status and applicable JSON length or explicit truncation errors
    Then it prints only the required summary and bounded failure tail
    And this summary is disclosed as a lossy projection rather than a complete terminal object
