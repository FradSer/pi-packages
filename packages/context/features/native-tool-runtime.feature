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

  Scenario: Research runs in a child Pi session via the shared worker
    Given the agent calls context_get with a research question
    When the tool starts its child Pi process through pi-kit's runPiWorker
    Then the child runs in print JSON mode without a session
    And its available tools are limited to read and bash
    And edit and write are excluded
    And the child receives a research-only prompt
    And the child runs in the caller's working directory with no sandbox
    And there is no wall-clock timeout and no result truncation

  Scenario: Repository clones stay prompt-level guidance
    Given the child needs line-level repository evidence
    When it inspects a public repository
    Then the prompt suggests git clone with depth 1 under /tmp
    And the prompt tells the child to remove its temporary clone after inspection

  Scenario: Research renders an informative call row while executing
    Given the agent calls context_get with a research query
    When the tool call is rendered in the TUI
    Then Pi renders an active context started row showing the query
    And a blank line follows the started row
    And Pi renders one compact expandable context lifecycle row when finished
    And expanding the researched row reveals the complete answer without line truncation

  Scenario: Research call rows fit the current TUI width
    Given a long research query with paths, CJK text and ANSI styling
    When the call component renders at widths 40, 80 and 160
    Then the started query wraps within the available display columns
    And it preserves the themed context prefix and the complete query without an ellipsis
    And whitespace and unsafe query escape sequences are sanitized

  Scenario: Research rows adapt when the TUI is resized
    Given a research query longer than 120 characters
    When the same call component renders wide, narrow and wide again
    Then the wide row shows the complete query when it fits
    And the narrow row wraps without omitting any query text
    And invalidation uses the current theme
    And the completed researched row also retains the complete query when it fits

  Scenario: Research shows a running status widget above the editor
    Given the agent calls context_get with a research question
    When the research child is running
    Then a status widget above the editor shows the researching query with live activity
    And the widget clears when research completes

  Scenario: Pi cancellation terminates the child process
    Given a context research child is still running
    When Pi aborts the tool execution signal
    Then the child process is terminated
    And the tool reports a cancellation error rather than a partial answer

  Scenario: A failed child process does not return an answer
    Given a Pi research child exits unsuccessfully
    When context_get completes
    Then the tool reports the child failure
