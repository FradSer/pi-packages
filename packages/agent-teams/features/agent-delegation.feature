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
    And the initial result includes Agent Presence showing 1 active Work Session

  Scenario: Leader checks presence of an idle Agent without prompt
    Given an Agent named "reviewer" has no pending inbox messages or active work
    When the leader calls agent with name "reviewer" without prompt
    Then the result synchronously reports status "idle"
    And no new model turn or child process is spawned

  Scenario: Temporary Agent promotion after verified success
    Given work is delegated to an unknown Agent name "data-migrator"
    And "data-migrator" executes as a Temporary Agent without Agent Memory
    When the Work Item passes verification with high-quality evidence
    Then the leader marks the Agent for promotion
    And a user-scoped Agent Definition is created for "data-migrator"
    And a dedicated Agent Memory folder is initialized for "data-migrator"
