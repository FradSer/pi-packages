Feature: Pi v1 runtime acceptance
  Scenario: The catalog executes through the real Pi agent
    Given an isolated Pi v1 session with a scripted local provider
    When it exercises each workflow route and legal transition
    Then results identify the actual procedure and active state
    And complete and cancel remove workflow-only tools
    And illegal transitions and undisclosed references fail without partial state writes

  Scenario: Session boundaries restore the selected work item
    Given a persisted active workflow with loaded references
    When Pi resumes it, navigates its tree, or compacts its context
    Then the current branch controls active tools
    And the restored procedure instructions reach the next model context

  Scenario: The newest persisted workflow record controls a real restart
    Given a temporary Pi session has an older active workflow record
    When a second real Pi v1 process reads a latest completed, cancelled, malformed, or invalid record
    Then workflow-only active tools are removed without resurrecting the older active record
    And no new hidden restore procedure or active workflow guidance reaches the provider context
    And invalid active records are persisted as cancelled with a validation reason

  Scenario: Terminal decisions use real keyboard input
    Given Pi presents an active workflow decision in a terminal
    When the user selects an option or enters a custom answer
    Then the tool returns the chosen answer
    When the user cancels selection or custom input, or the tool is aborted
    Then it leaves the decision pending

  Scenario: Every catalog disclosure is reachable through the native gateway
    Given every standalone root and workflow placement is derived from the current catalog
    When Pi loads each direct and transitive disclosure through its valid path
    Then the result exposes the requested canonical procedure source without partial workflow state
    And user-only capability roots reject model capability execution while disclosed references remain path-checked

  Scenario: Literal Matt Pocock commands preserve native routing and workflow state
    Given a fresh real Pi RPC session routes commands through the extension command registry
    When literal controls, aliases, malformed arguments, freeform requests, and menu responses are sent
    Then no-turn controls are confirmed by their RPC response and notify event while turn commands finish with native agent evidence
    And legal transitions, cancellation aliases, UI cancellation, and active workflow supersession preserve the expected persisted state
