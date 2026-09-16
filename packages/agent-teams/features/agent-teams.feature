Feature: Agent Teams final coordination surface
  Agent Teams exposes agent, work, and agent_event as its only model tools.

  Scenario: Final active tool maps contain no legacy tool
    Given the final extension is loaded for a leader or Worker
    When active tools are disclosed for its current role and Work state
    Then every model-visible coordination tool is agent, work, or agent_event
    And no removed lifecycle, message, or task tool is registered or granted

  Scenario: Worker capability grant contains final coordination tools
    Given a Worker starts with no optional execution tools
    Then its coordination grant contains agent_event and work
    And requested Pi built-ins are added without legacy coordination capabilities

  Scenario: Incompatible persisted Work snapshot fails explicitly
    Given persisted Work data has a different runtime version
    When Agent Teams initializes that runtime
    Then initialization fails with an incompatible runtime snapshot error
    And it does not silently discard or migrate that Work data

  Scenario: Agent event is communication-only
    Given a Leader or Worker sends an agent event
    Then the event may carry inform or request intent
    And it cannot complete, release, reopen, or assign Work

  Scenario: Exact Work assignment requires an incarnation handle
    Given an idle resident has a current spawn incarnation
    When the Leader assigns pending Work to that resident
    Then the target contains its exact session handle including the spawn identity
    And a name-only or stale handle is rejected without claiming Work
