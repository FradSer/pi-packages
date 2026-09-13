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
    Then the user shared file is ~/.pi/agent/harness.json
    And the project shared file is .pi/harness.json
    And the project personal file is .pi/harness.local.json
    And ~/.pi/agent/harness.local.json is ignored and absent from diagnostics
    And precedence is project personal over project shared over user shared
    And a policy name defined in several layers resolves to the innermost one
    And names listed in any layer's disabled list are removed everywhere

  Scenario: A matching tool call is blocked with corrective guidance
    Given a policy matches the bash command field against a pattern
    When the model invokes bash with a matching command
    Then the call is blocked
    And the block reason names the policy and states the correct procedure
    And the transcript records a display-only harness policy-blocked event with the policy reason

  Scenario: Observe actions report a matching call without blocking it
    Given a policy with the observe action
    When the model invokes a matching tool call
    Then the call proceeds without confirmation or blocking
    And the transcript records one display-only harness policy-observed event with the policy reason

  Scenario: Non-matching calls pass through untouched
    Given the same policy set
    When the model invokes a tool that matches no pattern
    Then the hook returns nothing and the call proceeds normally

  Scenario: Confirm actions defer to the user when UI exists
    Given a policy with the confirm action
    When a matching call arrives in an interactive session
    Then the user is asked to allow or deny it through a select dialog with the policy reason
    And choosing Allow once proceeds without blocking and records one policy-allowed event
    And choosing Block returns a block reason naming the user's choice and records one policy-blocked event
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

  Scenario: A /harness prompt creates a rule in the specified or default target
    Given the user provides a natural-language harness rule request
    When the user runs /harness with that request without scope flags
    Then the command targets the project personal layer at .pi/harness.local.json by default
    When the user specifies --global or --user
    Then the command targets the user shared layer at ~/.pi/agent/harness.json
    When the user specifies --shared or --project
    Then the command targets the project shared layer at .pi/harness.json
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

  Scenario: Existing and newly authored policies have an explicit check phase
    Given a policy omits its phase
    When the guardrail configuration is loaded
    Then the policy is assigned the tool-call phase
    And an output or artifact policy keeps its declared phase
    And existing tool-call regex rules continue to run before execution

  Scenario: Final assistant output is checked after it has streamed
    Given an output-phase policy matching prohibited assistant text
    When the final assistant message ends
    Then the harness records a checked output violation
    And it sends bounded corrective guidance back to the model
    And it does not claim that already streamed text was withheld

  Scenario: Actual written file content is checked after tool execution
    Given an artifact-phase policy matching prohibited file content
    When a write tool succeeds
    Then the harness reads the regular file at the written path
    And a matching file is recorded as a checked artifact violation
    And a matching string present only in the tool arguments does not count as an artifact match

  Scenario: Missing or unsafe artifact paths are reported as unsupported
    Given an artifact-phase policy and a write result whose path is missing, outside the workspace, or a symlink
    When the post-execution artifact check runs
    Then the harness records unsupported instead of checked
    And it does not send a repair for an artifact it could not safely inspect

  Scenario: Output and artifact repairs stop at a bounded limit
    Given a prohibited output or artifact remains after corrective guidance
    When the harness observes repeated violations
    Then it sends at most the configured repair limit
    And it records repair-exhausted without creating an infinite self-turn loop

  Scenario: Context guidance is a separate pre-generation surface
    Given a skill prompt is configured for an expanded skill invocation
    When context guidance is registered separately from guardrails
    Then the skill prompt is injected before generation
    And registering guardrails alone does not inject skill guidance
