Feature: Harness authoring preserves scope and meaning
  Scenario: Project configuration is the default
    Given a project without harness configuration
    When a user creates a harness rule without a scope flag or automatic consolidation learns one or AGENTS.md extracts skill guidance
    Then the target is .pi/harness.json
    And .pi/harness.local.json is used only on explicit personal configuration requests
    And no global harness.local.json is supported

  Scenario: Invalid existing guidance is not silently accepted
    Given an unknown bare-string CM5 skill prompt beside valid registered guidance
    When the configuration is validated for a write or loaded with a skill registry
    Then invalid entries are reported and excluded from runtime guidance
    And a write preserving invalid entries is rejected without changing the file
    And valid siblings still apply only to their expanded skill invocation
    And removing or repairing invalid data requires explicit user authorization

  Scenario: Preserve the user's semantic boundary
    Given a request that fullscreen popup means an overlay relationship
    When authoring instructions are generated
    Then they preserve the overlay relationship and ask before adding opacity, input, or scroll restrictions
    And persistence is not reported as trigger verification or global enforcement

  Scenario: Authoring steps describe the supported workflow positively
    Given a request to author a harness rule
    When authoring instructions and destination guidance are generated
    Then they lead with supported global ~/.pi/agent/harness.json and default project shared configuration with explicit personal choice
    And steps describe the exact target, valid structure, semantic preservation, and verification affirmatively
    And validation and authorization gates retain their existing behavior
