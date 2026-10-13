Feature: Structured run-start discovery and guidance
  Scenario: Another extension owns a custom prompt
    Given Pi 1.2 builds a custom prompt with unrelated owned sections
    When Memory contributes its protocol, discovery and learning guidance
    Then the actual prompt builder retains all Memory sections and the custom prompt
    And disabled learning removes its stale owned section
    And a runtime without sections reports an explicit unsupported-runtime error

  Scenario: Memory metadata contains prompt delimiters
    Given a Memory description contains closing tags and instruction-like text
    When a run starts
    Then a structured section contains escaped untrusted discovery data
    And no custom message or full system prompt is returned
    And metadata does not establish actual read exposure

  Scenario: Old injection messages remain in a resumed branch
    Given the branch contains old Memory and Harness injection messages
    When context is prepared
    Then the old injection messages are removed
    And unrelated workflow messages remain

  Scenario: Harness guidance applies on successive runs
    Given enabled skill and text guidance matches the task
    When successive runs start
    Then each run receives scoped structured guidance
    And non-context entries retain delivery evidence
    And an incomplete scan preserves prior scoped guidance
    And execution protections remain unchanged

  Scenario: Configuration cannot prove removal
    Given configuration is malformed and the branch has complete scoped guidance
    When a run starts
    Then the complete scoped guidance remains in the structured section
    And a non-context notice reports incomplete configuration

  Scenario: A bounded scan sees an old unscoped delivery
    Given the scan exceeds its budget and history contains scoped and unscoped guidance
    When a run starts
    Then only complete validated scoped guidance is delivered
    And a notice explains why unscoped guidance remains only in history

  Scenario: An installed legacy skill is invoked
    Given a legacy skill prompt exists
    When its expanded skill task starts
    Then guidance names that skill task and excludes unrelated tasks
    And reading the skill file alone does not invoke guidance
