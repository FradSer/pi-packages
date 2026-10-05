Feature: Bounded and interruptible monitor runtime
  Scenario: Monitor identities survive extension reloads
    Given two monitor manager instances from different session lifetimes
    When each starts a command
    Then their IDs differ and terminal evidence cannot overwrite an earlier command
  Scenario: Pathological JavaScript expressions cannot block the deadline
    Given a contract with catastrophic backtracking
    When command output triggers the expression
    Then the monitor times out and shutdown terminates its matcher
  Scenario: Stream idle windows are independent
    Given an unterminated stdout sentinel and continuous stderr progress
    When stdout is idle
    Then the stdout contract resolves successfully
  Scenario: Diagnostics preserve unterminated output
    Given a command writes an unterminated failure explanation
    When it times out or is stopped
    Then terminal diagnostics contain the explanation
  Scenario: Shutdown owns completed process groups
    Given a stopped or naturally completed shell has a descendant ignoring SIGTERM
    When the session shuts down
    Then shutdown waits for escalation and no descendant remains running
  Scenario: Unicode output obeys byte budgets
    Given large Unicode lines
    When diagnostics are retained and returned
    Then each line and the complete returned tail obey UTF-8 byte limits and truncation is visible
