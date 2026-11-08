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

  Scenario: A started row names what this run is learning from
    Given the current transcript ends with a real user request about a specific topic
    When a current-task learning run starts without a separate explicit memory request
    Then the one [learning] started row and the spinner activity name that topic
    And the subject is sanitized, collapsed to one bounded line and taken only from the real user entry
    And the row does not claim that any knowledge was already learned
    When the transcript has no readable user entry or the run is full-corpus maintenance
    Then the run falls back to naming its bounded mode instead of inventing a topic

  Scenario: The learning start is visible to the user
    Given an automatic or manual learning run begins
    When the parent starts the pipeline
    Then the transcript shows one [learning] started row naming the run
    And the terminal shows one final outcome row when the run ends
    And that row expands to a Markdown rendering of each applied safe Memory's description and body
    And the expansion omits frontmatter, filenames and receipt details
    And one spinner activity row shows above the editor while the run is active
    And that activity row is cleared when the run ends
    And no expandable receipt metadata is shown in either row

  Scenario: Headless use keeps its explicit form
    Given no interactive UI is available
    When the user enters /learning without arguments
    Then the parent prints the existing bounded learning status instead of opening a native menu
    And no learning worker starts
