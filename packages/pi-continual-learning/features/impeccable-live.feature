Feature: Impeccable Live direct-launch guidance
  A skill prompt can scope its guidance to the expanded skill invocation's user
  message, so a command-specific procedure does not bleed into other commands
  of the same skill.

  Scenario: Impeccable Live gets the macOS direct-launch procedure
    Given an impeccable system skill prompt with userMessagePattern "^live$"
    When its complete expanded skill invocation reaches before_agent_start with user message "live"
    Then the system prompt directs macOS to use open <served app URL>
    And it forbids helper serverPort and agent-browser
    And it keeps live-poll.mjs active in the foreground after the page connects

  Scenario: Impeccable Polish does not get Live startup guidance
    Given the same impeccable system skill prompt with userMessagePattern "^live$"
    When its complete expanded skill invocation reaches before_agent_start with user message "polish"
    Then the system prompt remains unchanged
