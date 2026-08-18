Feature: Read-only side questions
  The btw extension answers a side question in an isolated Pi child process
  without adding a session or leaving temporary prompt material behind.

  Background:
    Given the pi-btw-fradser extension is installed

  Scenario: A child Pi run is configured read-only
    When a side question starts
    Then the child runs in print JSON mode without a session
    And its allowed tools are read, grep, find, and ls
    And bash, edit, and write are excluded

  Scenario: A long side prompt exists only for the child lifetime
    Given a side prompt exceeds the command-line argument limit
    When the child is running
    Then the prompt is passed as a private temporary @file
    And the temporary @file exists while the child needs it
    When the child terminates
    Then the temporary prompt file and its containing directory are removed

  Scenario: A long side prompt is cleaned up when the child cannot launch
    Given a side prompt exceeds the command-line argument limit
    When the child process emits a launch error
    Then the side question returns a failed result
    And the temporary prompt file and its containing directory are removed

  Scenario: Multi-turn side questions include conversation history in the prompt
    Given an initial side question has been answered
    When a follow-up side question is asked
    Then the prompt includes the side conversation history
    And the prompt includes the new side question
    And the child process executes without persisting a session

  Scenario: The btw overlay covers the main session input area
    Given the main session has its input TUI visible
    When the btw overlay opens
    Then the overlay is rendered directly over the main session input area
    And the overlay has no bottom margin

  Scenario: Multi-turn overlay maintains turns and aggregates token usage
    Given an interactive side question overlay
    When an initial question and a follow-up question are answered
    Then the overlay displays all conversation turns
    And the overlay does not display a redundant header title for the initial question
    And each conversation turn displays its question with You and its answer with btw
    And the footer aggregates token usage and cost across turns
    And the follow-up composer uses two full-width horizontal separators instead of a boxed frame
    And the follow-up composer keeps equal spacing on both sides of the input area
    And conversation separators span the available width with equal side spacing
    And the overlay does not report nonexistent hidden lines
    And conversation separators are longer than the content text and centered

  Scenario: Side answers render Markdown formatting
    Given an interactive side question overlay
    When the side child returns an answer containing headings, emphasis, lists, and code
    Then the overlay renders the answer through the Markdown component
    And block-level Markdown at the start of an answer is not joined to the btw label

  Scenario: Side answers are constrained to concise responses
    Given a side question prompt is built
    When the child receives its instructions
    Then it is told to answer in at most five short bullets
    And it is told to stay within a short word or character budget
    And it is told not to repeat the question or write a report

  Scenario: Side context stays compact
    Given a current session contains many messages
    When the side question context is built
    Then at most four recent messages are included
    And the context is capped at 4000 characters

  Scenario: Excessive side output is capped before display
    Given the side child returns an unusually long answer
    When the JSONL output is parsed
    Then the displayed answer is capped at 6000 characters

