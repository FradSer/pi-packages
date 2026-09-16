Feature: Generalize harness lessons without broadening action surfaces
  Scenario: Direct requests and consolidation learn a reusable error class
    Given feedback about a mistake in one project document
    When direct harness generation or the consolidation planner translates that evidence
    Then it identifies the reusable error class before choosing a supported mechanism
    And incidental document tokens, row numbers, and verbatim phrases are not rule boundaries
    And resource identifiers are retained only for explicit resource-specific user requirements
    And it transfer-tests another same-kind document and a rephrasing
    And unrelated actions remain outside the rule rather than confirming all writes

  Scenario: Semantic lessons use an actual skill or report a limitation
    Given a semantic correction that cannot be safely recognized by regex tool-call gates
    When either harness generation surface chooses a mechanism
    Then it uses a skill-scoped entry (a flat skill rule, or legacy skillPrompts) only for an actual registered skill and its supported invocation
    And it does not invent a skill or claim global interception
    And if no safe supported mechanism exists it reports the limitation without adding a rule

  Scenario: Skill prompts use only registered skill keys and object entries
    Given the session exposes a finite set of registered skills
    When direct generation or consolidation proposes skillPrompts
    Then the proposal names an exact registered skill key, not a policy name
    And the entry is an object with prompt and target fields
    And an unknown skill key is rejected or omitted with a diagnostic
    And a JSON readback does not count as an effective trigger test
    And direct harness edits require a complete validated write instead of bypassing validation
    And unchanged stale entries may be preserved or removed
    And automated additions without a registry fail closed

  Scenario: Generalization preserves the exact target creation protocol
    Given a direct harness request with an authoritative target path
    When the generation prompt adds generalization guidance
    Then the existing exact read create verify sequence remains unchanged
    And direct authoring positively describes scoped confirmation, exact registered skills, and preservation when reporting limitations
