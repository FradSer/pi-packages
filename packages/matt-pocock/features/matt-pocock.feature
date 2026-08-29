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

  Scenario: A user manually transitions between phases
    Given an idea-to-ship workflow is active at the shaping phase
    When the user selects a later phase from the harness transition menu
    Then the harness persists the selected procedure and phase
    And it injects that procedure
    And it does not infer phase completion from model or tool activity

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

  Scenario: Agent asks the user questions via interactive selection tool
    Given an active grilling or interview procedure
    When the agent calls the matt_pocock_ask tool with question and options
    Then the tool presents choices using the Pi UI selection dialog
    And it supports recommended option, timeout fallback, and custom user input

  Scenario: The package has no recursively discoverable child skills
    Given pi-matt-pocock is packaged
    When Pi discovers its resources
    Then its manifest declares only the package-root extension
    And the package contains no SKILL.md file
    And its procedures remain plain Markdown resources

  Scenario: Deferred automation remains documented
    Given the first harness version is packaged
    When TODO.md is inspected
    Then it lists automatic completion inference
    And it lists automatic session creation
    And it lists automatic teammate creation
    And it lists tool-level BDD or TDD write blocking
    And it lists per-workflow commands
    And it lists a second public skill surface
