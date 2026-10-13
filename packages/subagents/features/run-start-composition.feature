Feature: Structured Agent Memory context
  Scenario: Memory composes with other run-start contributions
    Given a disk identity has capability entries
    And another extension contributes prompt sections and guidelines
    When a custom message starts a run without a prompt
    Then Agent Memory adds a bounded named prompt section
    And the section identifies memory as untrusted reference data
    And no full prompt override or custom message carries the memory
    And the other extension's contributions remain unchanged

  Scenario: Index metadata contains prompt delimiters
    Given an entry cue and the Memory path contain ampersands and prompt tags
    When the startup hook builds the Memory section
    Then the complete index encodes ampersands and angle brackets
    And one decoding pass recovers the exact read path
    And the encoded complete section remains within eight KiB
