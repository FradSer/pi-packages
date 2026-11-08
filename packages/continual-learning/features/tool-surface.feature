Feature: One tool surface owns parent tool names and active transitions

  Planner children receive an immutable inline dossier with --no-tools. Worker
  loadouts, worker CLI allowlists and the harness_check_cases tool are retired.
  Parent authoring tools and the dynamic current-source collector keep their
  own activation paths.

  Scenario: Parent learning tool activation preserves foreign tools
    Given a parent session exposes read, bash, edit and write
    When agent-triggered Memory learning is enabled
    Then learn is active
    And read, bash, edit and write remain active
    When agent-triggered Memory learning is disabled
    Then learn is inactive
    And read, bash, edit and write remain active

  Scenario: Harness authoring activates and resets its declared tools
    Given a parent session exposes read and write
    When a Harness authoring request starts
    Then harness_preview and harness_write are active alongside read and write
    When the session resets
    Then both Harness authoring tools are inactive
    And read and write remain active

  Scenario: No worker loadout or case tool is exported
    Given the package tool surface is loaded
    Then workerCliArgs and WORKER_LOADOUTS are not exported
    And harness_check_cases is neither a tool nor a tool name
    And learning_read survives as the frozen-dossier evidence marker and
        as the collector's own scoped read tool

  Scenario: Planner children get no tool allowlist
    When a Memory, Harness or AGENTS planner child is spawned
    Then it uses the literal --no-tools flag and an inline dossier
    And no planner tool_choice none transformation is emitted
