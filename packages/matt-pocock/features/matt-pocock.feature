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

  Scenario: A prompt cancels active workflow before rerouting
    Given a Matt Pocock workflow is active
    When the user invokes /matt-pocock with a new arbitrary engineering prompt
    Then the harness records that the current workflow was cancelled as superseded
    And it forwards the prompt for autonomous workflow or capability routing

  Scenario: A user explicitly selects a legal next procedure
    Given an idea-to-ship workflow is active at the shaping phase
    When the user selects a catalog-defined next procedure from the harness transition menu
    Then the harness persists the selected procedure and its catalog phase
    And it injects that procedure and its required dependency closure

  Scenario: An agent automatically transitions after completing a procedure
    Given an active idea-to-ship workflow has completed its shaping procedure
    When the next applicable procedure is clear from the workflow route
    Then the agent calls matt_pocock_active with that allowed target without waiting for user confirmation
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

  Scenario: Agent-document work uses a standalone capability without workflow state
    Given no workflow is active in the session
    When the user asks to create or edit a skill or agent instruction document
    Then the agent calls matt_pocock_workflow in capability mode for writing-for-agents
    And it does not create persistent engineering workflow state

  Scenario: A de-slop capability removes AI slop without workflow state
    Given no workflow is active in the session
    When the user asks to remove AI slop from the recent changes
    Then the agent calls matt_pocock_workflow in capability mode for deslop
    And it does not create persistent engineering workflow state
    And it rewrites fabricated evidence, evidence widening, defensive clutter, mock patching, and vacuous names while behavior, public interfaces, and test outcomes stay identical

  Scenario: The standards baseline rejects AI slop patterns in code review
    Given the code-review procedure builds its fixed standards baseline
    When the standards axis evaluates the diff
    Then the baseline includes cross-language AI slop patterns for fabricated evidence, evidence widening, defensive clutter, mock patching, and vacuous names
    And each pattern is a labelled judgement call overridden by a documented repository standard
    And the baseline skips any pattern that repository tooling already enforces

  Scenario: Agent autonomously starts a workflow through the baseline gateway
    Given a task matching a structured engineering workflow
    When the agent calls matt_pocock_workflow in workflow mode
    Then the harness activates the catalog entry for the requested route
    And the tool returns the entry procedure and required dependency closure
    And the session records the workflow state

  Scenario: Known procedure aliases normalize through the catalog
    Given the catalog records tight-red-loop and clarify-goal as known aliases
    When a consumer resolves either alias
    Then tight-red-loop resolves to diagnosing-bugs
    And clarify-goal resolves to wayfinder
    And workflow phase selection still comes from the catalog placement

  Scenario: The catalog is the single source of procedure truth
    Given the package bundles workflow, utility, reference, and asset resources
    When the procedure catalog is validated
    Then every bundled procedure resource is classified exactly once
    And every declared file, dependency, disclosure, alias, and transition resolves
    And every workflow route has exactly one entry with its title, menu label, and routing description
    And every internal reference has an inbound catalog edge

  Scenario: Starting a workflow loads its mandatory dependency closure
    Given improve-codebase-architecture requires the shared codebase-design vocabulary
    When the architecture workflow starts
    Then the tool result contains both procedure bodies with stable source identifiers
    And it lists optional references without loading every disclosed resource
    And the injected bundle remains within the configured size limit

  Scenario: A workflow advertises only legal next transitions
    Given an architecture workflow is active at improve-codebase-architecture
    When the workflow tool returns its state contract
    Then it lists only the catalog-defined next procedures and terminal actions
    And a transition outside that set fails with the allowed alternatives
    And it does not restart the route default

  Scenario: The agent explicitly completes or cancels a workflow
    Given a workflow is active
    When the agent completes or cancels it through the workflow tool
    Then the terminal status is persisted with its work item identity
    And active-only workflow tools are disabled
    And later turns receive inactive workflow guidance

  Scenario: Standalone capabilities are reachable without child skills
    Given the package bundles one-shot productivity and engineering capabilities
    When the user opens the Matt Pocock menu or the model selects a curated capability
    Then writing-for-agents and the other catalog utilities are available through the single gateway
    And running one does not create persistent workflow state
    And the package still contains no SKILL.md file

  Scenario: Conditional references load through the active gateway
    Given an active procedure or one of its required dependencies discloses a reference by catalog id
    When the agent loads that reference
    Then the gateway returns the referenced body with a stable source identifier
    And internal Markdown pointers use stable catalog source ids instead of unresolved relative paths
    And references outside the active procedure disclosure set are rejected

  Scenario: Procedure texts route agents through the catalog gateway, not Pi skills
    Given one procedure references another catalog procedure by id
    When the agent follows that reference
    Then model-reachable capabilities name matt_pocock_workflow mode capability
    And disclosed references name the matt_pocock_active load action
    And required dependencies are described as already bundled
    And no procedure text calls a catalog procedure a skill, arms a skill state, runs user-invoked setup, or points at available_skills

  Scenario: Loaded references survive workflow restoration
    Given an active workflow has loaded one or more disclosed references
    When the session restores that workflow state
    Then it validates the disclosure chain in order
    And it reinjects the root procedure, mandatory dependencies, and loaded references without duplicates
    And references disclosed by the restored references remain available

  Scenario: The active gateway is progressively disclosed
    Given no Matt Pocock workflow is active
    When a session starts
    Then transition, load, complete, cancel, and interview operations are inactive
    When a workflow starts
    Then those active-state operations become available
    When the workflow reaches a terminal state
    Then those active-state operations become inactive again

  Scenario: A stale restored workflow explicitly cancels after validation fails
    Given the session branch contains a workflow state with an unavailable procedure
    When the harness fails to restore that workflow
    Then it records a cancelled terminal workflow state for other extensions
    And it warns with the catalog-defined valid procedures for that route

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

  Scenario: A recommended decision automatically adopts the recommendation on timeout
    Given an active grilling or interview procedure
    When the agent calls matt_pocock_ask with a recommended option
    And the selection times out
    Then the tool automatically selects the recommended option
    And it does not leave the decision pending

  Scenario: A decision without a recommendation has no timeout and remains pending when unanswered
    Given an active grilling or interview procedure
    When the agent calls matt_pocock_ask without a recommended option
    Then the selection dialog has no timeout
    When the selection is cancelled, Pi has no UI, or custom input is blank
    Then the tool reports that the decision is pending user input
    And it does not authorize workflow progression

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

  Scenario: Upstream synchronization metadata is verifiable
    Given the package records its selected upstream resources and intentional exclusions
    When the upstream sync contract is checked and the package is packed
    Then the compared commit, comparison tag, and resolved tag commit are distinct fields
    And every selected upstream skill maps to a catalog capability with the recorded invocation mode
    And ignored upstream skills carry an explicit reason
    And the packed package includes the selection metadata and offline checker

  Scenario: A local-only capability stays out of the upstream selection metadata
    Given deslop is a local capability with no upstream origin
    When the upstream selection metadata is validated
    Then every selected entry still maps to an upstream skill and a catalog capability
    And the local capability is not listed as selected or excluded upstream content

  Scenario: Deferred lifecycle automation remains documented
    Given the first harness version is packaged
    When TODO.md is inspected
    Then it lists automatic session creation
    And it lists automatic teammate creation
    And it lists tool-level BDD or TDD write blocking

  Scenario: Native macOS dialog is guarded against non-macOS and SSH environments
    Given the native dialog helper
    When a dialog is requested on linux, win32, an SSH session, CI, or with PI_NO_NATIVE_DIALOG set
    Then the helper reports the native dialog as unsupported
    And macOS dialogs raise on unsupported environments and enforce a three-button limit

  Scenario: Native dialog configuration defaults to disabled and respects user opt-in
    Given a configuration file path or absence in ~/.pi/agent/pi-matt-pocock.json
    When loading the package configuration
    Then it defaults to native dialogs disabled
    And it enables native dialogs only when useNativeDialog is explicitly true

  Scenario: Native dialog presents choice list and opens an input dialog for custom answers
    Given native macOS dialog is enabled and supported
    When the agent asks a structured question with options
    Then it presents a native choice list dialog
    And the dialog title is derived from an explicit tool title or active workflow context
    And selecting custom input opens a native text input dialog for typing the answer
    And timeout with recommendation automatically adopts the recommended option

  Scenario: The harness offers a default start-a-task entry in the menu
    Given no Matt Pocock workflow is active
    When the user invokes /matt-pocock without arguments
    Then the harness presents Start a task first alongside manual route selection
    When the user selects Start a task
    Then the harness forwards the conversation context for autonomous workflow routing and execution
    And it does not require the user to manually pick a route

  Scenario: Starting a new task supersedes the active workflow
    Given a Matt Pocock workflow is active
    When the user selects Start a task from the harness menu
    Then the harness records that the current workflow was cancelled as superseded
    And it forwards the conversation context for autonomous workflow or capability routing
