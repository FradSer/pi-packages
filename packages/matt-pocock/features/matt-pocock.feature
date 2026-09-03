Feature: Matt Pocock workflow harness
  Expose Matt Pocock engineering workflows through one Pi harness command
  without globally discoverable child skills.

  Scenario: The harness opens one workflow-routing menu
    Given a Pi session has loaded pi-matt-pocock
    When the user invokes /matt-pocock without arguments
    Then the harness presents the available workflow routes
    And it does not register one command per workflow

  Scenario: Selecting a route injects its procedure
    Given the user selects the hard-bug diagnosis route
    When the harness activates the route
    Then it persists diagnosing-bugs as the current procedure at the feedback-loop phase
    And it injects the diagnosing-bugs procedure into the session

  Scenario: Active workflow state survives a session restart
    Given the harness persisted a workflow route and phase in a custom session entry
    When the session starts again on that branch
    Then the harness restores the latest workflow state and procedure guidance
    And it does not add a duplicate visible workflow lifecycle event
    And it does not add an input-footer status

  Scenario: A prompt routes to and begins the relevant workflow
    Given no Matt Pocock workflow is active
    When the user invokes /matt-pocock with an arbitrary engineering prompt
    Then the harness forwards the prompt for autonomous workflow routing and execution
    And it does not reject the prompt as an unknown route

  Scenario: A prompt ends active workflow before rerouting
    Given a Matt Pocock workflow is active
    When the user invokes /matt-pocock with a new arbitrary engineering prompt
    Then the harness records that the current workflow ended
    And it forwards the prompt for autonomous workflow routing and execution

  Scenario: A user explicitly overrides the automatic phase transition
    Given an idea-to-ship workflow is active at the shaping phase
    When the user selects a later phase from the harness transition menu
    Then the harness persists the selected procedure and phase
    And it injects that procedure

  Scenario: An agent automatically transitions after completing a procedure
    Given an active idea-to-ship workflow has completed its shaping procedure
    When the next applicable procedure is clear from the workflow route
    Then the agent calls matt_pocock_workflow for that procedure without waiting for user confirmation
    And the harness persists and returns the new procedure and phase

  Scenario: Active work receives concise phase guidance
    Given a workflow is active
    When an agent turn starts
    Then the harness adds compact workflow and phase guidance
    And it does not inject every procedure into the system prompt

  Scenario: Inactive sessions receive workflow routing guidance
    Given no workflow is active in the session
    When an agent turn starts
    Then the harness adds guidance on available engineering workflows and how to activate them

  Scenario: Routine document work does not activate an engineering workflow
    Given no workflow is active in the session
    When the user asks to create a test document through another skill
    Then the agent does not call matt_pocock_workflow
    And it follows the relevant skill without introducing an unrelated engineering workflow

  Scenario: Agent autonomously starts or transitions a workflow via tool
    Given a task matching a structured engineering workflow
    When the agent calls the matt_pocock_workflow tool
    Then the harness activates the requested route and procedure
    And the tool returns the procedure instructions
    And the session records the workflow state

  Scenario: A hard-bug workflow accepts the tight-red-loop entry point
    Given the agent is diagnosing a hard bug
    When it activates the tight-red-loop procedure at the reproduce phase
    Then the harness loads the diagnosing-bugs instructions
    And the session records the diagnosing-bugs procedure at the reproduce phase

  Scenario: A wayfinding workflow accepts the clarify-goal entry point
    Given the agent is starting a large ambiguous initiative
    When it activates the clarify-goal procedure for the wayfinding route
    Then the harness loads the wayfinder instructions
    And the session records the wayfinder procedure without rejecting the request

  Scenario: The workflow tool advertises every valid procedure name
    Given the matt_pocock_workflow tool schema
    Then the procedure parameter enumerates every bundled route procedure and known alias
    And every route procedure resolves to a bundled procedure file

  Scenario: An unknown procedure soft-lands on the route default
    Given the agent activates wayfinding with an invented procedure name
    When the harness processes the tool call
    Then it activates the wayfinder default procedure at the mapping phase
    And the tool result names the rejected procedure and the valid alternatives
    And it instructs the agent not to switch routes

  Scenario: A stale restored workflow explicitly ends after validation fails
    Given the session branch contains a workflow state with an unavailable procedure
    When the harness fails to restore that workflow
    Then it records an explicit workflow exit for other extensions
    And it warns with the valid procedures for that route

  Scenario: Workflows advance through every non-user-owned next step
    Given an active Matt Pocock workflow has enough confirmed context to perform its next step
    When the current procedure completes its summary, decision, or ticket resolution
    Then it does not stop to recommend or ask whether to continue
    And it begins or transitions to the next applicable workflow work without waiting for further confirmation
    And it continues through newly unblocked AFK work until only a genuinely user-owned decision, unavailable fact, or required external action remains

  Scenario: Structured interview questions are available only during an active workflow
    Given the structured interview tool is initially active
    When the session starts without a Matt Pocock workflow
    Then the active tool list excludes matt_pocock_ask
    When the agent activates a Matt Pocock workflow
    Then the active tool list includes matt_pocock_ask
    When the workflow ends
    Then the active tool list excludes matt_pocock_ask again
    When the session restores an active Matt Pocock workflow
    Then the active tool list includes matt_pocock_ask

  Scenario: Agent asks the user questions via interactive selection tool
    Given an active grilling or interview procedure
    When the agent calls the matt_pocock_ask tool with question and options
    Then the tool presents choices using the Pi UI selection dialog
    And it supports a recommended option and custom user input

  Scenario: A user-owned decision remains pending without an answer
    Given an active grilling or interview procedure
    When the matt_pocock_ask selection times out, Pi has no UI, or custom input is cancelled or blank
    Then the tool reports that the decision is pending user input
    And it does not select a recommended option or authorize workflow progression

  Scenario: The package has no recursively discoverable child skills
    Given pi-matt-pocock is packaged
    When Pi discovers its resources
    Then its manifest declares only the package-root extension
    And the package contains no SKILL.md file
    And its procedures remain plain Markdown resources

  Scenario: Matt Pocock tool rows use operation-specific prefixes
    Given a Matt Pocock workflow or structured interview tool result
    When Pi renders its collapsed lifecycle row
    Then a workflow row label is [matt pocock] started ·
    And a structured interview row label is [matt pocock] ask ·
    And the operation appears outside the bracketed prefix

  Scenario: Workflow activation uses the monitor-style started row
    Given a Matt Pocock workflow tool result contains a loaded procedure for the model
    When Pi renders the user-facing workflow row
    Then it shows [matt pocock] started · followed by the route and phase as one native Text row
    And it has no lifecycle background band or expansion hint
    And it does not render the procedure text as user-facing details

  Scenario: A structured answer keeps question and answer visible in the collapsed row
    Given a Matt Pocock structured interview result contains a question and answer
    When Pi renders the collapsed ask row
    Then its first row shows the question
    And its second row shows the answer
    And the row remains expandable for non-duplicated metadata

  Scenario: A multiline structured answer renders each line cleanly without raw newlines
    Given a Matt Pocock structured interview result contains a multiline answer
    When Pi renders the collapsed ask row
    Then no rendered TUI row contains a raw newline
    And the first answer line shows the answer label
    And subsequent answer lines remain visible in separate rendered rows

  Scenario: Workflow status clears use the shared Pi-kit transient-status adapter
    Given the workflow lifecycle clears its status entry
    When a session starts, restores, ends, or transitions a workflow
    Then it clears the matt-pocock status through pi-kit's status adapter

  Scenario: Workflow notifications use the shared Pi-kit notification adapter
    Given the workflow command needs to notify the user of a status or validation outcome
    When it emits that notification
    Then it delegates notification sanitization and delivery to pi-kit

  Scenario: Packed package resolves workspace dependency protocols
    Given the package declares workspace dependencies for local development
    When the package is packed for distribution
    Then the packed manifest resolves @fradser/pi-kit to a concrete semver version
    And it contains no workspace protocol dependencies

  Scenario: The package documents its Chinese workflow-harness architecture
    Given a user needs to understand how pi-matt-pocock differs from the upstream skill collection
    When they open the package README
    Then it links to the Chinese architecture guide
    And the guide explains route selection, on-demand procedure loading, session persistence, and the schema trade-off

  Scenario: Deferred lifecycle automation remains documented
    Given the first harness version is packaged
    When TODO.md is inspected
    Then it lists automatic session creation
    And it lists automatic teammate creation
    And it lists tool-level BDD or TDD write blocking
    And it lists per-workflow commands
    And it lists a second public skill surface
