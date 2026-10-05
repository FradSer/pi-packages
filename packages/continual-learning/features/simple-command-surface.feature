Feature: Simple continual-learning command surface
  The everyday interface exposes six focused command forms while preserving
  advanced and compatibility commands for scripts and recovery.

  Background:
    Given the pi-continual-learning package is installed

  Scenario: Memory opens three top-level management areas
    When the user opens `/memory`
    Then the panel offers `Browse memories`, `Learning settings`, and `Recent learning`
    And phase policies are nested under `Advanced`
    And a history item offers `Undo`

  Scenario: An explicit Memory request remains manual when automatic learning is off
    Given automatic learning is off
    When the user enters `/memory Remember that this project uses pnpm`
    Then the parent validates a bounded Memory-only proposal
    And the request does not write Harness or AGENTS.md
    And the request may produce no write when validation finds no durable safe lesson
    And a parent-owned receipt reports the outcome

  Scenario: Harness scope is chosen in the panel
    When the user opens `/harness`
    Then the panel shows active rules and lets the user choose the write scope
    And a rule submitted from the panel uses the selected scope
    When the user enters `/harness Require pnpm test before publishing`
    Then the parent-validated command form targets project shared configuration by default

  Scenario: The six primary commands stay compact
    Then `/memory` is the Memory management panel
    And `/memory <request>` is an explicit Memory request
    And `/consolidate` learns from the current task
    And `/consolidate full` performs full maintenance
    And `/harness` is the Harness rules panel
    And `/harness <request>` authors a rule through the selected scope

  Scenario: Compatibility commands retain their safety boundaries
    Then `/memory undo <change-id> --yes` is required for headless undo
    And `/consolidate backfill` reports reference status only
    And legacy model, status, policy, history, evaluate, and Harness scope forms remain accepted
