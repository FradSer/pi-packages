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

  Scenario: Final learning result expands to the generated Memory content
    Given a completed learning run that applied Memory entries
    When the learning result is rendered collapsed
    Then the user sees one final outcome line with an expand affordance
    And no usage, cost, source, calls, status, summary or attempt details are shown
    When the user expands the result
    Then every applied Memory filename and body is readable, including harness-only private entries
    And a body whose frontmatter is followed by a blank line is still readable with all its sections
    But credential-shaped content is never shown in the terminal
    And the complete receipt remains available to the model and stored on disk
    And no usage, cost, source, calls, status or attempt details are shown expanded

  Scenario: A result without applied Memory stays one unexpandable row
    Given a completed learning run that applied no safe Memory entries
    When the learning result is rendered collapsed and expanded
    Then the user sees one final outcome line in both states
    And no expand affordance or Memory body is shown
    And the complete receipt remains available to the model and stored on disk

  Scenario: A running learning pipeline shows one live activity row
    Given an automatic or manual learning run is active in the TUI
    When its phases select sources, plan, review and write changes
    Then one spinner activity row is shown above the editor for the run
    And the row names the run without usage, cost or receipt metadata
    And the row is cleared when the run ends, is cancelled or fails
    And errors and safety holds are still reported as warning or error notices
    And the Harness authoring procedure remains an inline message for the model

  Scenario: Partial learning failure
    Given Memory applied a change and Harness failed
    When the final learning result is rendered
    Then its one line reports both the applied change and the failed phase

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
    And Harness authoring starts with one compact inline procedure row
    And the complete procedure remains available to the model

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
