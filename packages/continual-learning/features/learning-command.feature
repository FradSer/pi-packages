Feature: One learning command entry
  The user learns through /learning. The parent owns every mutation and
  evidence check; the model is not asked to name or call learning tools.
  /learning is the only documented user entry. Frozen research protocols
  keep their internal command bindings, but those are not user entry points.

  Scenario: Open one command menu
    Given the pi-continual-learning package is installed
    When the user opens /learning without arguments
    Then the panel offers Remember this request, Learn from this task, Maintain all knowledge, Manage Harness rules, and Settings / history / undo
    And no custom user-interaction tool is registered
    And Manage Harness rules opens the guarded authoring procedure directly,
        without depending on a registered /harness command

  Scenario: An explicit request is handled by the parent
    Given automatic learning is off
    When the user enters /learning remember this request
    Then the parent freezes the current task evidence and runs a Memory-only learning pipeline
    And the request does not write Harness or AGENTS.md
    And a parent-owned receipt reports the outcome

  Scenario: A final row names the applied knowledge
    Given a current-task learning run applied one Memory record
    When the run ends
    Then the transcript shows one final [learning] outcome row naming the applied Memory
    And the user can expand that row to read the applied Memory's description and body
    And the row never claims that knowledge was applied before the run ended

  Scenario: Headless use keeps its explicit form
    Given no interactive UI is available
    When the user enters /learning without arguments
    Then the parent prints the existing bounded learning status instead of opening a native menu
    And no learning worker starts
