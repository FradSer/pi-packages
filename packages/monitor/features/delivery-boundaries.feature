Feature: Monitor terminal delivery at the Pi tool boundary
  Background:
    Given the monitor extension is loaded in Pi v1.0

  Scenario: A mixed tool batch waits for the terminal contract
    Given a UI-host assistant batch calls monitor_start and an ordinary tool
    When the monitor command reaches its terminal result
    Then monitor_start returns that terminal result in the same call
    And the next provider request cannot precede that terminal result
    And no asynchronous monitor-result message is sent for that monitor

  Scenario: A nested monitor call returns its terminal result to its caller
    Given a UI-host assistant calls another tool that executes monitor_start
    When the monitor reaches its terminal result
    Then the nested monitor call returns the terminal report directly
    And no asynchronous monitor-result message is sent for that monitor

  Scenario: An independent monitor batch retains asynchronous delivery
    Given every tool in the UI-host assistant batch is monitor_start
    When a monitor starts
    Then it returns its pending acknowledgement with terminate true
    And its one terminal message includes the monitor ID in content and details

  Scenario: A synchronous terminal tool result renders its outcome
    Given monitor_start has returned a synchronous failure result
    When the tool result is rendered
    Then the lifecycle row identifies the failure outcome
    And expanding the row shows terminal diagnostics

  Scenario: Capture limits are disclosed to every result consumer
    Given a terminal match contains captures exceeding their aggregate budget
    When the terminal report is delivered or expanded
    Then its text and expanded details identify capture truncation
    And its displayed millisecond duration is rounded for readability
