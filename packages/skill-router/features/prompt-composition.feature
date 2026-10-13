Feature: Additive run guidance
  Scenario: Preserve structured prompt ownership
    Given existing prompt sections and an owner-supplied custom prompt
    When the package adds its run guidance
    Then it sets its own named prompt section
    And the actual Pi builder retains the owner prompt and package guidance
    And it returns no system prompt override or custom message

  Scenario: Handle a custom run without a user prompt
    Given a custom-message run without a prompt
    When the before-agent-start hook runs
    Then it does not interpret the custom message as a user request
    And existing guidance and state boundaries remain intact
