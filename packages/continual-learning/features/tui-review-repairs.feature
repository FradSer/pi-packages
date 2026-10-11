Feature: Readable and truthful learning management
  Scenario: Long lists and details in a short narrow terminal
    Given a 48 column terminal with long records and document bodies
    When the user navigates or scrolls
    Then focus, navigation and close controls remain visible
    And every body line is reachable without adding chat notifications

  Scenario: Return from a detail
    Given a selected Memory, history or Harness record
    When the user closes its details
    Then the previous list retains its position

  Scenario: Partial learning failure
    Given Memory applied a change and Harness failed
    When the learning result is collapsed
    Then it reports both the applied change and the failed phase

  Scenario: Model search and width
    Given long model names and a 48 column terminal
    When the user types jev or key
    Then all characters enter the query and every rendered line fits

  Scenario: Understand policies and diagnostics
    Given automatic phase policies and more than eight diagnostics
    When management opens
    Then current policy and automatic-only scope are explained
    And all diagnostics can be read

  Scenario: Semantic lifecycle rows
    Given failed, blocked or incomplete outcomes
    When the row renders
    Then its colors match its status
    And Harness authoring starts with one compact procedure row

  Scenario: Reflow preserves reading intent
    Given a reader scrolled to the middle of a document
    When the same live terminal changes width
    Then the same logical text remains at the top
    And a reader already at the end remains at the end

  Scenario: Nested settings navigation
    Given an open automatic phase policy
    When the user cancels
    Then the phase list returns before the settings list
    And the settings list retains its selected action

  Scenario: Readable controls and safe reader defaults
    Given a narrow terminal and a selected history or Harness rule
    When management renders
    Then history identifies the target before timestamp metadata
    And Enter and Esc hints are complete
    And reading a rule defaults to Close
    And policy help is separate from its short title
    And learning results omit generic event labels
