Feature: Development checks use one Pi core cohort across the split chain

  Scenario: Host-provided Pi peers resolve to the root development version
    Given kit, subagents, tasks and agent-teams publish Pi core as wildcard peers
    And the user selected Pi 1.3.0 as the locked development cohort
    And the root has that locked Pi development cohort
    When package-level verification resolves coding-agent or pi-tui
    Then each split package uses the same version as the root
    And explicit development requirements do not become published runtime dependencies

  Scenario: Fork history supports the selected core and old persisted tool metadata
    Given a current Pi tool result or an older result carrying addedToolNames
    When subagents snapshots a completed exchange for a child
    Then parent-only details and legacy tool activation are removed
    And original conversation text and parent state remain intact
    And the implementation typechecks against the selected development core

  Scenario: Refreshing dependencies does not silently upgrade unrelated packages
    Given a development Pi peer-cohort alignment
    When pnpm updates the split packages
    Then their peers stay wildcard compatible with the installed Pi host
    And only their development dependency requirements are pinned
