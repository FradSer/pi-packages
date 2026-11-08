Feature: Simple continual-learning command surface

  /learning is the single documented user entry. Its menu delegates to the
  parent-owned handlers; the parent keeps every validation, write and receipt.
  Frozen research protocols retain their internal command bindings, but those
  are provenance fixtures, not documented user commands.

  Background:
    Given the pi-continual-learning package is installed

  Scenario: The learning menu covers every everyday action
    When the user opens /learning
    Then the panel offers remember, learn from task, maintain all knowledge,
        manage Harness rules, and settings / history / undo
    And phase policies are nested under Advanced
    And a history item offers Undo
    And no old command is offered as an entry point

  Scenario: An explicit Memory request remains manual when automatic learning is off
    Given automatic learning is off
    When the user enters /learning remember this request
    Then the parent validates a bounded Memory-only proposal
    And the request does not write Harness or AGENTS.md
    And the request may produce no write when validation finds no durable safe lesson
    And a parent-owned receipt reports the outcome

  Scenario: Harness authoring keeps its guarded scope
    When the user opens /learning and selects Manage Harness rules
    Then the parent opens the same guarded Harness authoring procedure
    And a submitted rule uses the selected scope and the parent's
        positive/negative case evaluation, confirmation and atomic write
    And no registered /harness command is required

  Scenario: One everyday command is compact
    Then /learning is the single documented command entry
    And /learning <request> is an explicit Memory or rule request
    And /learning without arguments opens the management menu
    And /memory, /consolidate and /harness are not documented or suggested

  Scenario: Headless and recovery behavior stay honest
    Given no interactive UI is available
    When the user enters /learning without arguments
    Then the parent prints the bounded learning status instead of a native menu
    And headless undo still requires an explicit change id and --yes
    And an explicit backfill reports reference status only
