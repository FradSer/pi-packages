Feature: Isolated Pi research tool
  To research external code without expanding the main Pi tool surface
  As a user of @fradser/pi-context
  I want one tool that delegates research to a read-only child Pi process

  Scenario: Context registers one research tool
    Given the context package is installed in Pi
    When Pi loads the package extension
    Then it registers only the context_get tool
    And it does not register a /context command

  Scenario: Natural language requests trigger context retrieval
    Given the context package is installed in Pi
    When the user asks to research or get external context in natural language
    Then Pi guides the agent to invoke context_get automatically
    And the user does not need to type the tool name or a slash command

  Scenario: Research runs in an isolated child Pi session
    Given the agent calls context_get with a research question
    When the tool starts its child Pi process
    Then the child runs in print JSON mode without a session
    And its available tools are limited to read and bash
    And edit and write are excluded
    And the child receives a research-only prompt

  Scenario: Research may clone a repository only in the temporary directory
    Given the child needs line-level repository evidence
    When it inspects a public repository
    Then it may git clone with depth 1 under /tmp
    And it removes its temporary clone after inspection
    But it does not modify the caller's working directory

  Scenario: Research results are bounded and rendered as one lifecycle result
    Given the child Pi process returns a research answer
    When context_get completes
    Then the answer is bounded before it enters the main session
    And Pi renders one compact expandable context lifecycle row

  Scenario: Pi cancellation terminates the child process
    Given a context research child is still running
    When Pi aborts the tool execution signal
    Then the child process is terminated
    And the tool reports a cancellation error rather than a partial answer

  Scenario: A failed child process does not return an answer
    Given an isolated Pi research child exits unsuccessfully
    When context_get completes
    Then the tool reports the child failure
