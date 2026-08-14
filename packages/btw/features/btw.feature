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
