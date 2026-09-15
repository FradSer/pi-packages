Feature: Isolated Pi research tool
  To research external code without expanding the main Pi tool surface
  As a user of @fradser/pi-context
  I want one tool that delegates research to an independent prompt-constrained Pi process with read and bash

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

  Scenario: Research runs the context package's bundled agent via the shared worker
    Given the agent calls context_get with a research question
    When the tool starts its child Pi process through pi-kit's runPiWorker
    Then the child runs in print JSON mode without a session
    And its available tools are limited to read and bash
    And edit and write are unavailable because only read and bash are allowlisted
    And extension, skill, prompt-template, context-file, and theme discovery are disabled
    And pi-kit loads the child prompt from the context package's bundled agents/context-researcher.md
    And the user research question is appended to that bundled agent prompt
    And the child runs in the caller's working directory with no sandbox
    And there is no wall-clock timeout and no result truncation

  Scenario: Repository clones stay prompt-level guidance
    Given the child needs line-level repository evidence
    When it inspects a public repository
    Then the prompt suggests git clone with depth 1 under /tmp
    And the prompt tells the child to remove its temporary clone after inspection

  Scenario: Research starts with one stateless identity
    Given the agent calls context_get with a research query
    When the research child starts
    Then Pi renders one native Text row in the `[agent] @conext-research started · agents/context-researcher.md` shape
    And only the `[agent]` prefix uses the custom message label color
    And every research invocation uses the fixed @conext-research identity
    And each child uses no Pi session and retains no agent memory between invocations
    And the completed tool contributes no second agent-start row
    And Pi does not render a `[context] researched` lifecycle row
    And the complete answer remains model-facing without transcript details

  Scenario: Research rows fit the current TUI width
    Given a context research agent starts
    When the started and completed components render at widths 40, 80 and 160
    Then the started row stays within the available display columns
    And the completed renderer contributes zero transcript lines
    And neither renderer exposes the model-facing research answer

  Scenario: Research rows adapt when the TUI is resized
    Given a context research agent starts
    When the started component renders wide, narrow and wide again
    Then the row retains the same agent identity and definition path when they fit
    And invalidation uses the current theme
    And the completed renderer remains empty

  Scenario: Research shows the child agent's latest running status above the editor
    Given the agent calls context_get with a research question
    When the research child is running
    Then a status widget above the editor identifies the child agent with the same @conext-research name
    And the widget shows the latest tool, thinking, or answer activity
    And newer activity replaces older activity
    And the widget clears when research completes

  Scenario: Pi cancellation terminates the child process
    Given a context research child is still running
    When Pi aborts the tool execution signal
    Then the child process is terminated
    And the tool reports a cancellation error rather than a partial answer

  Scenario: Empty successful research retries for a final answer
    Given a Pi research child exits successfully without a textual final answer
    When context_get reaches its final response step
    Then it retries the research once with a prompt requiring a self-contained final answer
    And the retry preserves the original research request and tool constraints
    And a successful retry becomes the tool result
    And only an empty retry reports that research returned no answer

  Scenario: A failed child process does not return an answer
    Given a Pi research child exits unsuccessfully
    When context_get completes
    Then the tool reports the child failure without retrying
    And the result renderer shows one error line instead of hiding it with the empty success renderer
