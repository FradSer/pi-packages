Feature: One documented learning command and one model tool

  The user-facing surface is /learning. The model calls one zero-argument
  learn tool. Old worker loadouts and the retired harness_check_cases tool
  are gone. Frozen research protocols keep their internal command bindings;
  those are provenance fixtures, not documented user entry points.

  Background:
    Given the pi-continual-learning package is installed

  Scenario: The command list documents only /learning
    When a user reads the command reference
    Then /learning is the only documented everyday entry
    And /memory, /consolidate and /harness are not offered as user entry points
    And no documentation or guidance tells the user to type an old command

  Scenario: The Harness menu uses the guarded procedure directly
    Given a user opens /learning and selects Manage Harness rules
    When the parent opens the Harness authoring procedure
    Then it uses the same startRuleProcedure gate as the learn Harness route
    And it does not depend on a registered /harness command
    And exact candidate/predecessor bytes, positive and negative cases,
        confirmation and atomic write remain enforced

  Scenario: Retired worker tool surface is gone
    Given the package exports its tool surface
    Then workerCliArgs and WORKER_LOADOUTS are not exported
    And harness_check_cases is not a registered tool or a tool name
    And tool_choice none is not emitted for learning planner children
    And the learning_read evidence marker survives byte-identical

  Scenario: Active parent tools still work without worker loadouts
    Given learn and harness_write are defaultActive false
    When an agent request enables learning and opens Harness authoring
    Then learn and the guarded Harness write tool are activated by the parent
    And the dynamic current-source collector keeps its own scoped read tool
    And no planner child receives a tool allowlist

  Scenario: Frozen provenance commands remain internal bindings
    Given the frozen research protocols drive native maintenance commands
    Then their /memory and /consolidate argv and command markers are unchanged
    And those bindings appear in no user documentation, menu or model guidance
    And frozen proofs, fixtures and SHA256 manifests stay byte-identical
