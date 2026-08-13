Feature: Consolidate artifact validator
  Machine-check G2/G3/G4/G7 planning artifacts and privacy so
  /memory "Consolidate memory now" cannot claim done on cosmetic-only runs.

  Background:
    Given a harness memory directory and a public .memory directory
    And planning artifacts inventory, cluster map, and staleness table

  # --- cluster coverage (G2) ---

  Scenario: Cluster map covers every inventory file exactly once
    Given inventory lists project_a.md and project_b.md
    And cluster map places each in a theme cluster
    When I run the cluster coverage check
    Then the check passes

  Scenario: Cluster map missing an inventory file fails
    Given inventory lists project_a.md and project_b.md
    And cluster map only lists project_a.md
    When I run the cluster coverage check
    Then the check fails with "missing from cluster"

  Scenario: Cluster map with duplicate membership fails
    Given inventory lists project_a.md
    And cluster map lists project_a.md in two clusters
    When I run the cluster coverage check
    Then the check fails with "duplicate"

  Scenario: Cluster map with unknown file not in inventory fails
    Given inventory lists project_a.md
    And cluster map lists project_a.md and orphan.md
    When I run the cluster coverage check
    Then the check fails with "not in inventory"

  # --- staleness coverage (G3) ---

  Scenario: Staleness table scores every inventory file
    Given inventory lists project_a.md and feedback_b.md
    And staleness assigns KEEP and SUPERSEDED respectively
    When I run the staleness coverage check
    Then the check passes

  Scenario: Staleness missing a file fails
    Given inventory lists project_a.md and project_b.md
    And staleness only scores project_a.md KEEP
    When I run the staleness coverage check
    Then the check fails with "missing from staleness"

  Scenario: Invalid staleness verdict fails
    Given inventory lists project_a.md
    And staleness scores project_a.md as MAYBE
    When I run the staleness coverage check
    Then the check fails with "invalid verdict"

  # --- report ground-truth paths (G4/G7) ---

  Scenario: Report with path arrow rows passes when project files exist
    Given inventory lists project_deploy.md
    And report contains "src/deploy.ts → found"
    When I run the report ground-truth check
    Then the check passes

  Scenario: Report without path rows fails when project_* present
    Given inventory lists project_deploy.md
    And report has no path arrow lines and no N/A ground-truth
    When I run the report ground-truth check
    Then the check fails with "path"

  Scenario: Report may use N/A when no repo
    Given inventory lists project_deploy.md
    And report contains "Ground truth: N/A (no repo)"
    When I run the report ground-truth check
    Then the check passes

  Scenario: Report without path rows passes when only feedback_* inventory
    Given inventory lists feedback_pref.md only
    And report has no path arrow lines
    When I run the report ground-truth check
    Then the check passes

  # --- privacy fail-closed ---

  Scenario: Harness-only file must not exist under public .memory
    Given harness MEMORY.md marks feedback_pref.md as (harness only)
    And feedback_pref.md exists under public .memory
    When I run the privacy check
    Then the check fails with "harness only"

  Scenario: Public MEMORY.md must not contain harness-only lines
    Given public MEMORY.md contains a line with (harness only)
    When I run the privacy check
    Then the check fails with "harness only"

  Scenario: Clean privacy split passes
    Given harness MEMORY.md marks feedback_pref.md as (harness only)
    And feedback_pref.md exists only in harness
    And public .memory has only safe files
    And public MEMORY.md has no (harness only) lines
    When I run the privacy check
    Then the check passes

  # --- full gate ---

  Scenario: Full validate passes only when all selected checks pass
    Given valid inventory, cluster, staleness, report, and privacy layout
    When I run the full validator
    Then exit code is 0

  Scenario: Full validate fails closed on any single failure
    Given valid artifacts except cluster missing one file
    When I run the full validator
    Then exit code is 1
