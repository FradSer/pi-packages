Feature: Preserve enforced Harness configuration across a flat-rule upgrade
  New authoring uses flat rules. Existing policy and skillPrompt declarations
  are read-only compatibility inputs, never automatically rewritten or weakened.

  Scenario: Existing narrow project protection does not lock out Bash
    Given a personal legacy layer protects .memory.local writes and kit source creation of createPackageAgentRun
    When the registered gate sees harmless Bash, protected writes and edits, and deletion-only edits
    Then Bash and deletion-only edits are allowed
    And protected writes and replacement text are blocked
    And loading leaves every config byte unchanged
    And compatibility notices are not validation errors

  Scenario: Mixed layers preserve override and disabled semantics
    Given all three layers contain legacy and flat declarations
    When nearest same-name legacy policies and skill prompts replace outer definitions
    Then legacy disabled names accumulate across all layers for policies and same-ID flat declarations
    And a legacy policy replaces only its equivalent built-in default, not other manually authored flat rules
    And block dominates confirm and observe across both formats with one confirmation at most

  Scenario: Invalid legacy scope is conservative without becoming universal
    Given an invalid legacy write-only policy shadows a valid outer policy
    When write and Bash calls are evaluated
    Then writes remain unexecuted until repair and unrelated Bash is allowed
    But genuinely unknown legacy scope holds all tool calls
    And read and validated complete writes to Harness configuration may bypass incomplete checks for recovery
    But valid matching protection still applies to those configuration tools

  Scenario: Existing skill prompts retain their original delivery target
    Given a legacy skill prompt with a userMessagePattern and a system or user target
    When its skill is expanded with a matching user suffix
    Then its exact prompt reaches the configured target alongside applicable flat guidance
    And skill document text or a plain read never substitutes for the user suffix
    And Harness-owned guidance does not trigger other text guidance

  Scenario: Existing output and artifact protections remain operational
    Given legacy output and artifact policies
    When finalized output or an in-workspace regular artifact violates a policy
    Then the existing bounded checker reports the violation and requests repair
    And observe only records and already-visible output is never claimed retracted
    And unsupported artifact reads are reported without escaping workspace or size bounds

  Scenario: New flat rules coexist with immutable legacy containers
    Given a valid legacy-only target and parent-owned provenance
    When the native writer or automatic planner adds a non-conflicting flat rule
    Then existing legacy container values and provenance remain unchanged
    And legacy names are reserved against automatic identity collisions
    And new or modified legacy declarations are rejected
    And removal requires a native before-and-after protection-loss preview with explicit approval
    And headless removal preserves original bytes

  Scenario: Approval is bound to the exact native write arguments
    Given a complete valid replacement is awaiting its native confirmation preview
    When its content or path changes while confirmation is pending
    Then approval is invalid even for an equivalent path alias
    And the call stays unexecuted with the original configuration untouched
