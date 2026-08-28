Feature: Main-session-first plan mode
  As a user starting /plan
  I want the main session to plan before any worker starts
  So that simple tasks do not pay for unnecessary worker processes

  Scenario: A plan request starts in the main session
    Given /plan receives a planning prompt
    When the command handles the prompt
    Then it enters read-only plan mode
    And it sends the prompt as a follow-up to the main session
    And it does not start plan workers immediately

  Scenario: Plan mode prompts emphasize exploration first and mention built-in workers
    Given plan mode is active
    When the system prompt and main-session prompt are rendered
    Then the system prompt instructs to explore the codebase first before designing
    And the main-session prompt instructs to explore the codebase first before designing
    And the system prompt mentions that built-in workers are available for parallel exploration
    And the main-session prompt mentions that built-in workers are available for parallel exploration

  Scenario: The main-session plan is shown before optional research
    Given the main session writes a plan file
    When the planning turn ends
    Then the plan review overlay is shown
    And worker research remains agent-controlled

  Scenario: Plan completion does not loop review commands to the agent
    Given the main session completes writing a plan
    When the planning turn ends
    Then the plan review overlay is displayed directly without sending review messages to the agent
    And the active plan request is cleared to prevent repeated review triggers

  Scenario: Worker research is decided by the main-session agent
    Given the main session has written a plan
    When the plan marks worker research as required
    Then plan workers start automatically with the existing plan as context
    And no manual research command or menu action is required

  Scenario: Plan mode shows a persistent indicator below the editor
    Given the user enters plan mode
    When the plan mode indicator is rendered
    Then a "plan mode on" marker is shown below the input editor
    And the marker is removed when plan mode is exited

Feature: Plan worker diagnostics and CLI compatibility
  As a user running /plan
  I want plan workers to have the same visible running state as teammates
  So that I can tell which exploration or writing phase is active and diagnose failures

  Scenario: Plan workers render a live above-editor status widget
    Given /plan starts explore and plan-writer workers
    When worker progress changes during plan generation
    Then the plan widget shows each worker phase and running status
    And each row is formatted as worker id, label in parentheses, and current activity
    And the spinner and task name appear before the separator
    And a worker without live activity shows "Working..." after the separator
    And the widget is rendered above the input editor
    And the widget uses the shared pi-kit spinner cadence
    And the widget is cleared after plan generation finishes

  Scenario: Plan worker failures remain visible until cleanup
    Given an explore worker reports a failed result
    When plan generation is still handling the result
    Then the plan widget marks that worker as failed
    And cleanup does not happen before the plan result is handled

  Scenario: Explore workers avoid unsupported CLI options
    Given a plan worker launches an explore child with a working directory
    When the child Pi command is constructed
    Then it does not include the unsupported --cwd option
    And explore workers include --no-extensions

  Scenario: Explore workers cannot mutate the project
    Given an explore worker is launched
    When its child tools are configured
    Then bash and write tools are not available to the explore worker
    And read-only exploration remains enforced outside the prompt

  Scenario: The plan writer cannot mutate paths outside the plan file
    Given a plan writer is launched
    When its child tools are configured
    Then bash and write tools are not available to the plan writer
    And the host writes only the returned plan content to the configured plan path
    And the writer child runs with extensions disabled

  Scenario: Failed explore workers expose status and diagnostics
    Given an explore child exits without findings and reports an error
    When the plan worker records the child result
    Then the explore result status is failed
    And its diagnostics include the child error
    And the aggregate failure identifies the affected focus

  Scenario: Empty successful output is not reported as completed
    Given an explore child exits successfully without structured findings
    When the plan worker records the child result
    Then the explore result status is failed
    And its diagnostics say that no structured result was produced

  Scenario: Manual worker research commands are not exposed
    Given plan mode is active
    When the user enters /plan research or /plan workers
    Then the command is not treated as a worker research request

  Scenario: Plan workers do not use wall-clock timeouts
    Given a plan worker is launched
    When the child process is running
    Then pi-kit does not accept a timeoutMs option
    And plan-mode does not report a timed-out worker state

  Scenario: Plan writer receives structured explore status
    Given one or more explore results have status and diagnostics
    When the plan writer prompt is assembled
    Then each result includes its status and diagnostics

  Scenario: Plan writer completion requires a fresh non-empty plan
    Given a writer exits successfully without returning plan content
    When plan worker generation finishes
    Then the writer is marked failed
    And an existing plan is not reported as a newly completed plan

  Scenario: Finished plan worker tool activity does not remain current
    Given a plan worker has streamed a tool call followed by new thinking or text
    When the worker progress is rendered
    Then the widget shows the new thinking or text instead of the finished tool label

  Scenario: Plan review reserves space for its action menu
    Given the plan review overlay is rendered in a short terminal
    When its body viewport is calculated
    Then all plan actions and footer remain within the overlay height

  Scenario: Plan review timeout defaults to a fresh implementation session
    Given the plan review overlay is waiting for a user choice
    When the review timeout elapses without a selection
    Then the overlay selects Start fresh and implement
    And the plan is sent through the replacement session context
    And the original session does not receive the implementation request
