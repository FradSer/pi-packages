Feature: Generic tool-call guardrails from layered config
  A package-level hook evaluates declarative policies against every tool
  call. Matching calls are blocked with an instructive reason that teaches
  the model the correct procedure instead of leaving it stuck, while
  non-matching calls pass through untouched. Confirm gates own the agent
  loop while their dialog waits, so an unanswered dialog must fail closed
  after a bounded wait instead of hanging the session.

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
    And the transcript records a display-only harness policy-blocked event with the policy reason

  Scenario: Non-matching calls pass through untouched
    Given the same policy set
    When the model invokes a tool that matches no pattern
    Then the hook returns nothing and the call proceeds normally

  Scenario: Confirm actions defer to the user when UI exists
    Given a policy with the confirm action
    When a matching call arrives in an interactive session
    Then the user is asked to allow or deny it through a select dialog with the policy reason
    And choosing Allow once proceeds without blocking and records a policy-allowed event
    And choosing Block returns a block reason naming the user's choice and records a policy-blocked event
    And without UI the call is blocked instead of silently allowed

  Scenario: An unanswered confirm dialog fails closed after a bounded wait
    Given a policy with the confirm action
    When a matching call arrives and nobody answers before the dialog timeout
    Then the select dialog carries a bounded timeout with a visible countdown
    And the expired dialog resolves to no choice
    And the call is blocked with a reason stating the confirmation timed out

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

  Scenario: The /harness command reports the active surface
    Given guardrails loaded from one or more layers
    When the user runs /harness
    Then the command reports sources, policy names, and the config paths
    And it works headlessly without interactive UI

  Scenario: A /harness prompt creates a global rule
    Given the user provides a natural-language harness rule request
    When the user runs /harness with that request
    Then the command sends one follow-up with an explicit file-creation protocol
    And the protocol targets only ~/.pi/agent/harness.local.json
    And a missing target is initialized there instead of being searched for elsewhere
    And it preserves existing rules and asks the agent to verify the resulting JSON

  Scenario: A matching skill prompt records the applied prompt in the transcript
    Given a project-local skill prompt for an expanded skill
    When the skill prompt is injected into the system prompt
    Then the transcript records a display-only harness skill-prompt event with the actual prompt as its subject
    And the event details identify its target, configuration layer, and configuration file
    And the collapsed event does not substitute the configuration filename for the prompt
    And its standard expand-key hint remains visible when the prompt is truncated
    And expansion wraps the complete prompt rather than truncating it

  Scenario: Unsupported policy fields are rejected with actionable schema diagnostics
    Given a policy uses legacy scope and rule fields instead of declarative fields
    When the guardrail configuration is loaded
    Then the malformed policy is skipped
    And the diagnostic names the unsupported fields and the accepted tools, paths, pattern, action, and reason fields
    And a valid declarative policy in the same layer remains active
