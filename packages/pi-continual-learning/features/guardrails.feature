Feature: Generic tool-call guardrails from layered config
  A package-level hook evaluates declarative policies against every tool
  call. Matching calls are blocked with an instructive reason that teaches
  the model the correct procedure instead of leaving it stuck, while
  non-matching calls pass through untouched.

  Scenario: Layered config resolves with deterministic precedence
    Given guardrails are declared in the user directory and the project
    When the configuration is loaded
    Then the user file is ~/.pi/agent/harness.json plus its .local variant
    And the project file is .pi/harness.json plus its .local variant
    And a policy name defined in several layers resolves to the innermost one
    And names listed in any layer's disabled list are removed everywhere

  Scenario: A matching tool call is blocked with corrective guidance
    Given a policy matches the bash command field against a pattern
    When the model invokes bash with a matching command
    Then the call is blocked
    And the block reason names the policy and states the correct procedure

  Scenario: Non-matching calls pass through untouched
    Given the same policy set
    When the model invokes a tool that matches no pattern
    Then the hook returns nothing and the call proceeds normally

  Scenario: Confirm actions defer to the user when UI exists
    Given a policy with the confirm action
    When a matching call arrives in an interactive session
    Then the user is asked to allow or deny it
    And without UI the call is blocked instead of silently allowed

  Scenario: Broken policies never break the session
    Given a config containing an invalid regex or malformed JSON
    When tool calls are evaluated
    Then broken policies are skipped and reported once
    And valid policies continue to apply

  Scenario: Built-in defaults ship with the package and can be disabled
    Given the package ships curated default policies for known futility
    When no user or project config exists
    Then the defaults are active
    And any layer can disable a default by name

  Scenario: Require gates AND-scope a policy to a class of calls
    Given a policy with a require gate on the file path and violation patterns
      on the written content
    When the model edits a UI file containing a violating fixed width
    Then the call is blocked with corrective design guidance
    And the same violation in a non-UI file passes through untouched

  Scenario: The /guardrails command reports the active surface
    Given guardrails loaded from one or more layers
    When the user runs /guardrails
    Then the command reports sources, policy names, and the config paths
    And it works headlessly without interactive UI
