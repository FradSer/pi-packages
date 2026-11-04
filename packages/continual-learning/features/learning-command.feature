Feature: One learning command entry
  The user learns through /learning. The parent owns every mutation and
  evidence check; the model is not asked to name or call learning tools.
  Advanced command forms remain available in this layer for scripts and
  recovery, and the existing Harness authoring gate is unchanged.

  Scenario: Open one command menu
    Given the pi-continual-learning package is installed
    When the user opens /learning without arguments
    Then the panel offers Remember this request, Learn from this task, Maintain all knowledge, Manage Harness rules, and Settings / history / undo
    And no custom user-interaction tool is registered
    And Manage Harness rules points to the unchanged /harness guarded authoring gate

  Scenario: An explicit request is handled by the parent
    Given automatic learning is off
    When the user enters /learning remember this request
    Then the parent freezes the current task evidence and runs a Memory-only learning pipeline
    And the request does not write Harness or AGENTS.md
    And a parent-owned receipt reports the outcome

  Scenario: The learning start is visible to the user
    Given an automatic or manual learning run begins
    When the parent starts the pipeline
    Then the transcript shows one [learning] started row naming the run
    And the terminal shows one final outcome row when the run ends
    And the run does not show a progress widget or expandable receipt details

  Scenario: Headless use keeps its explicit form
    Given no interactive UI is available
    When the user enters /learning without arguments
    Then the parent prints the existing bounded learning status instead of opening a native menu
    And no learning worker starts
