Feature: Flat skill rules provide invocation-scoped context
  Skill guidance is a rules entry with an identity independent from the exact
  registered skill selector. It supplements an expanded invocation through a
  retained conversation message, not a system-prompt mutation.

  Scenario: Layer resolution uses rule identity rather than skill name
    Given user and project layers declare the same rule id
    When the flat rules are resolved
    Then the project declaration completely replaces the user declaration
    And independent ids matching the same skill remain independently applicable

  Scenario: Every matching valid skill rule contributes its instructions
    Given two enabled rules selecting the same registered skill
    And a third rule selecting another skill
    When that exact skill is evaluated
    Then both matching rule identities and their instructions are returned
    And the unrelated skill rule is not returned

  Scenario: Expanded invocations receive retained task-scoped guidance
    Given a valid skill rule in project harness.json
    When before_agent_start receives Pi's expanded registered skill invocation
    Then the context adapter returns a harness-guidance custom message
    And its model-visible text identifies the rule and limits guidance to that skill task
    And message details identify the skill and contributing rule ids
    And retaining the message does not broaden the instruction's scope
    And the system prompt is not rewritten to carry the guidance

  Scenario: Skill availability is validated independently from invocation matching
    Given an unknown skill declaration beside a valid registered skill rule
    When the configuration is resolved with the session skill registry
    Then the unknown declaration has a diagnostic
    And the valid independent sibling remains available
    And registration alone is not reported as a verified trigger or successful task outcome

  Scenario: The skill-rule schema has no legacy target or suffix matcher
    Given a complete harness write with a skill rule
    When it contains target, prompt, or userMessagePattern fields
    Then validation rejects unsupported fields
    And accepted user-maintained fields are id, optional enabled, skill and instructions
    And an unchanged invalid predecessor is not silently accepted
    And automatic skill additions without a registry fail closed

  Scenario: Guidance requires no interactive confirmation
    Given a valid skill rule and an expanded registered invocation
    And no interactive UI is available
    When the context adapter prepares generation
    Then it returns the contextual message without a user-input dialog
    And it does not claim that delivery guarantees compliance or global interception
