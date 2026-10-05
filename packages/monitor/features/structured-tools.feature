Feature: Structured monitor tool results and cancellation
  Scenario: A codemode script consumes a terminal result without parsing text
    Given a nested monitor with a JSON terminal sentinel
    When the native Pi codemode executor waits for the monitor
    Then the script reads the terminal status and parsed JSON from structured data
    And no duplicate custom terminal message is sent

  Scenario: Invalid JSON remains visible to programmatic callers
    Given a matched sentinel with an invalid json capture
    When the monitor returns its terminal result
    Then structured data includes the parse error and original capture

  Scenario: An already cancelled tool never starts a process
    Given an aborted tool signal
    When monitor_start is called with a command that creates a marker
    Then no process starts and the marker is absent

  Scenario: Cancelling a nested monitor stops its command
    Given a nested monitor awaiting a terminal sentinel
    When its calling tool is cancelled
    Then the wait fails and the command cannot create its later marker

  Scenario: A background monitor survives completion of its initiating turn
    Given an asynchronous monitor acknowledgement
    When the initiating turn ends and its signal is cancelled
    Then the monitor still delivers its terminal result once

  Scenario: Failed tool calls show their error rather than a startup acknowledgement
    Given monitor_start or monitor_stop fails before returning details
    When Pi renders the error tool result
    Then the row shows failure and the original error text

  Scenario: Matcher startup fails before an asynchronous acknowledgement
    Given a monitor-only tool batch whose matcher worker cannot start
    When monitor_start returns
    Then the tool contains the terminal failure and structured failure status
    And it neither terminates the turn nor emits a duplicate custom message
