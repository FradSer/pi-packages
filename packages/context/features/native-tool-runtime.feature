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

  Scenario: Research runs the context package's bundled prompt via the shared worker
    Given the main session calls context_get with a research question
    When the tool starts its one-shot Pi worker through pi-kit's runPiWorker
    Then the child runs in print JSON mode without a session
    And its available tools are limited to read and bash
    And edit and write are unavailable because only read and bash are allowlisted
    And extension, skill, prompt-template, context-file, and theme discovery are disabled
    And the context package's typed prompt builder reads its bundled Markdown as a reference protocol rather than using the file as the prompt
    And it builds a task-specific prompt containing the current research request, caller working directory, reference protocol, and completion contract
    And the complete user research question remains model-facing without becoming a prompt resource identity
    And the child runs in the caller's working directory with no sandbox
    And there is no wall-clock timeout and no result truncation

  Scenario: Repository clones stay prompt-level guidance
    Given the child needs line-level repository evidence
    When it inspects a public repository
    Then the prompt suggests git clone with depth 1 under /tmp
    And the prompt tells the child to remove its temporary clone after inspection

  Scenario: Research starts with its concrete prompt
    Given the main session calls context_get with a research query
    When the research child starts
    Then Pi renders one native text row in the `[context] research started · <research query>` shape
    And exactly one blank line follows the started row
    And the concrete query is normalized and width-bounded for display
    And a different query produces a different started row
    And the row does not expose a Markdown prompt resource path
    And only the `[context]` prefix uses the custom message label color
    And each child uses no Pi session and retains no memory between invocations
    And the completed tool contributes no second worker-start row
    And the running tool renders no duplicate progress row in the transcript
    And Pi renders one compact expandable `[context] researched` lifecycle row when finished
    And expanding the researched row reveals the complete answer without line truncation

  Scenario: Research call arguments are still streaming
    Given Pi renders context_get before its query argument arrives
    When the call row renders with a missing or non-string query
    Then it shows context request without throwing
    And subsequent string query updates show the normalized concrete research query

  Scenario: Research rows fit the current TUI width
    Given a context research worker starts
    When the started and completed components render at widths 40, 80 and 160
    Then the started row stays within the available display columns
    And the completed row stays within the available display columns
    And expanding the completed row reveals the complete answer without line truncation

  Scenario: Research rows adapt when the TUI is resized
    Given a context research worker starts
    When the started component renders wide, narrow and wide again
    Then the row retains the same concrete research query when it fits
    And invalidation uses the current theme
    And the completed renderer retains the same request

  Scenario: Research shows the one-shot worker's latest running status through pi-kit's live activity widget
    Given the main session calls context_get with a research question
    When the research child is running
    Then pi-kit's live activity widget above the editor identifies the worker as researcher
    And the widget shows the latest tool, thinking, or answer activity
    And newer activity replaces older activity
    And the widget clears when research completes

  Scenario: Live research activity renders Markdown in its compact row
    Given a running research worker streams Markdown activity
    When its widget renders bold text, inline code, a link, or a heading
    Then pi-kit renders the activity through Pi's Markdown using the theme Pi injects into the widget
    And well-formed markdown elements keep that theme's native tokens instead of literal markup
    And a fence line is dropped because a streamed fence carries no content
    And the spinner and research identity remain on one width-bounded row
    And the identity and activity rendering come from pi-kit so every package's status row uses the same language
    And terminal control sequences in activity are sanitized before Markdown rendering
    And an activity with no visible width leaves an identity-only row
    And newer activity and theme invalidation replace the previous rendering

  Scenario: Pi cancellation terminates the child process
    Given a context research child is still running
    When Pi aborts the tool execution signal
    Then the child process is terminated
    And the tool reports a cancellation error rather than a partial answer

  Scenario: Empty successful research retries for a final answer
    Given a Pi research child exits successfully without a textual final answer
    When context_get reaches its final response step
    Then it retries the research exactly once with a prompt requiring a self-contained final answer
    And the retry tells the worker to complete the original request without relying on hidden reasoning or prior tool output
    And the retry preserves the original research request and tool constraints
    And a successful retry becomes the tool result
    And only an empty retry reports that research returned no answer

  Scenario: A failed child process does not return an answer
    Given a Pi research child exits unsuccessfully
    When context_get completes
    Then the tool reports the child failure without retrying
    And the result renderer shows the request and one sanitized error line on the error background

  Scenario: Transcript result blocks use pi lifecycle backgrounds
    Given a research query with unsafe escape sequences and long answer lines
    When the registered tool renders partial progress and its final result
    Then partial progress renders no transcript row while running
    And successful blocks use toolSuccessBg across every visible line
    And failed and cancelled blocks use toolErrorBg across the request and error
    And the expand hint comes from the app.tools.expand keybinding
    And terminal control sequences are sanitized before rendering
    And widths and theme changes preserve the background and request
