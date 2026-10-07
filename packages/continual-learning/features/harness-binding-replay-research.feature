Feature: Compare repair prompts on the same frozen original input
  Scenario: Only the new binding instructions differ
    Given the original read-only repair task and hash-checked evidence
    When the research prepares a second prompt
    Then all original protocol, errors, identities and citations remain unchanged
    And only the production binding instructions and binding table are inserted
  Scenario: A generated repair changes original identity or citations
    Given a real native read-only repair output
    When parent structure and original retention are checked
    Then changed identity or any citation property is rejected before real Jev verification
    And no research candidate is written or applied
