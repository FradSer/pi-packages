Feature: Agent Delegation and Work Item Lifecycle
  As a project leader
  I want to delegate work to named persistent Agents
  So that execution occurs in isolated Work Sessions without manual process management

  Background:
    Given the pi-agent-teams-fradser extension is loaded

  Scenario: Leader delegates new work to an existing Agent
    Given a persisted Agent named "reviewer" exists in user scope
    When the leader calls agent with name "reviewer" and prompt "Audit auth middleware"
    Then a new Work Item is created with a unique work ID
    And an isolated Work Session starts for "reviewer"
    And the initial result reports the actual starting execution state, open work ID, and precise route
    And another prompt without work starts independent work even while that Agent is running

  Scenario: Leader checks presence of an idle Agent without prompt
    Given an Agent named "reviewer" has no pending inbox messages or active work
    When the leader calls agent with name "reviewer" without prompt
    Then the result synchronously reports status "idle"
    And no new model turn or child process is spawned

  Scenario: Inspection distinguishes execution from assignment ownership
    Given unknown and defined Agents and residents that are starting, working, idle, or stopped
    When the leader inspects each Agent
    Then presence reflects the current runtime state without spawning
    And each actual Work Session reports its work ID, precise route, execution state, and open assignment ownership
    And no synthetic active session count is returned

  Scenario: Existing work is steered or explicitly reopened
    Given a resident has an open or closed assignment
    When the leader provides a matching work ID and prompt
    Then existing work is routed through leader messaging without spawning
    And only a matching closed work ID permits reopening
    And the work ID stays stable while the new assignment attempt receives fresh completion evidence
    And invalid work IDs fail without side effects even during inspection
    And a not-sent control outcome includes the recorded terminal report

  Scenario: Model override preserves the role definition
    Given a defined Agent with a role prompt and model
    When the leader delegates with an override model
    Then the override is passed to the runtime without replacing the role definition

  Scenario: Leader events report actual routing outcomes
    Given a leader event to a resident is queued or not sent
    When the event tool returns
    Then it reports the routing outcome without claiming delivery
    And missing routes, leader self routes, and report statuses are rejected

  Scenario: Worker communication registration includes lifecycle hooks
    Given the worker capability host supports tool registration and lifecycle subscriptions
    When worker capabilities are registered
    Then agent_event is registered and included in the worker tool universe
    And message lifecycle subscriptions track assignment bindings

  Scenario: Unknown delegation requires an explicit role contract
    Given an Agent name has no definition
    When the leader delegates a prompt to that name
    Then the tool rejects with guidance to define the role through teammate_spawn
    And the rejection names every checked definition scope
    And the rejection lists the agents available now
    And the rejection points at the shipped role reference for the inline definition
    And no capability-empty temporary worker is spawned

  Scenario: Temporary Agent promotion after verified success
    Given work is delegated to an unknown Agent name "data-migrator"
    And "data-migrator" executes as a Temporary Agent without Agent Memory
    When the Work Item passes verification with high-quality evidence
    Then the leader marks the Agent for promotion
    And a user-scoped Agent Definition is created for "data-migrator"
    And a dedicated Agent Memory folder is initialized for "data-migrator"
