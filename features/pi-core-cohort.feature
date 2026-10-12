Feature: Development checks use one Pi core cohort across all extension packages

  Scenario: Host-provided Pi peers resolve to the root development version
    Given all extension packages publish Pi core as wildcard peers
    And the user selected Pi 1.1.0 as the locked development cohort
    And the root has that locked Pi development cohort
    When package-level verification resolves coding-agent or pi-tui
    Then each extension package uses the same version as the root
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

  Scenario: TypeBox is provided by the selected Pi host
    Given Pi 1.1.0 bundles TypeBox 1.3.27
    When an extension imports the host-provided schema library
    Then its published TypeBox peer is wildcard compatible per the Pi package guide
    And a development-only version requirement may select the tested schema version
    And TypeBox is not bundled as an extension runtime dependency

  Scenario: Shared native subagent acceptance uses the selected Pi cohort
    Given the repository Pi core packages resolve to version 1.1.0
    When the shared native subagent fixture validates its runtime
    Then it admits exactly version 1.1.0 before running its isolated print and PTY cases
    And stale version expectations cannot prevent those cases from exercising the runtime
