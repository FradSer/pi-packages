Feature: Skill-invocation prompt guidance
  The harness can layer corrective guidance by skill name. Guidance applies only
  to Pi's fully expanded skill invocation, not raw commands or arbitrary text.

  Scenario: Project skill prompt overrides the user layer
    Given user and project harness.json files define the same skill prompt
    When the expanded skill invocation reaches before_agent_start
    Then the project definition is selected

  Scenario: System guidance is appended once
    Given a system-target skill prompt is configured
    When the same expanded skill event is handled twice
    Then the guidance is present in the system prompt only once

  Scenario: Matching requires Pi's complete expanded skill XML
    Given a skill prompt is configured
    When before_agent_start receives a raw /skill command or malformed XML
    Then no guidance is injected

  Scenario: User-target guidance uses one custom context message per turn
    Given a user-target skill prompt is configured
    When duplicate handlers receive fresh expanded-skill events in the same turn
    Then one hidden custom message carries the guidance
    And a later turn receives the guidance again
    And the original expanded user prompt is not rewritten

  Scenario: Unknown and unconfigured skills pass through
    Given no matching skill prompt is configured
    When an expanded skill invocation reaches before_agent_start
    Then the system prompt and messages remain unchanged

  Scenario: System guidance is safe in a headless session
    Given a system-target skill prompt is configured
    And no interactive UI is available
    When the expanded skill invocation reaches before_agent_start
    Then guidance is appended without prompting or failing
