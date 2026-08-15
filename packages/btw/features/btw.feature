Feature: Read-only side questions
  The btw extension answers a side question in an isolated Pi child process
  without adding a session or leaving temporary prompt material behind.

  Background:
    Given the @fradser/pi-btw extension is installed

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

  Scenario: Multi-turn overlay maintains turns and aggregates token usage
    Given an interactive side question overlay
    When an initial question and a follow-up question are answered
    Then the overlay displays all conversation turns
    And the footer aggregates token usage and cost across turns

