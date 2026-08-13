Feature: Background process monitoring
  The monitor extension runs a shell command in the background and streams its
  stdout to the agent as notifications, so the agent reacts to logs, deploys,
  CI runs, or file changes the moment something happens — no polling loops.

  Background:
    Given the @fradser/pi-monitor extension is loaded

  Scenario: Starting a monitor streams stdout to the agent
    When monitor_start runs with a command and description
    Then a background process is spawned for the command
    And the tool returns a monitor id immediately without blocking
    And each batch of stdout lines wakes the agent as a "[monitor ...]" notification

  Scenario: Output lines are batched within a window
    Given a monitor is running
    When multiple stdout lines arrive within 200ms
    Then they are combined into a single notification

  Scenario: stderr does not trigger notifications
    Given a monitor is running
    When the command writes to stderr
    Then no notification is sent
    And stderr is captured and reported when the monitor ends

  Scenario: A non-persistent monitor auto-stops after its timeout
    Given a non-persistent monitor with a timeout
    When the timeout elapses
    Then the process is killed
    And the agent is notified that the monitor timed out

  Scenario: A persistent monitor runs until stopped or the session ends
    Given a monitor is started with persistent=true
    Then it is not subject to a timeout
    And it keeps running across turns until monitor_stop or session shutdown

  Scenario: A monitor auto-stops after too many notifications
    Given a monitor is running
    When it emits more than the notification cap
    Then the process is killed
    And the agent is notified that the monitor hit the event limit

  Scenario: Stopping a monitor
    Given a monitor is running
    When monitor_stop runs with its monitor_id
    Then the process is killed and no completion notification is sent

  Scenario: Listing active monitors
    Given several monitors are running
    When monitor_list runs
    Then it returns each monitor's id, description, command, status, and notification count

  Scenario: Session shutdown cleans up all monitors
    Given monitors are running
    When the session shuts down
    Then every background process is killed

  Scenario: A match filter suppresses noisy lines
    Given a monitor is started with a match pattern
    When the command prints matching and non-matching lines
    Then only matching lines wake the agent
    And non-matching lines are counted as suppressed
    And the suppressed count is reported when the monitor ends

  Scenario: A running monitor is surfaced in the UI
    Given monitors are running
    Then a widget below the input box shows "N monitor(s) running"
    And no global input listener is registered
    When the user opens /monitor
    Then a full-screen console lists the monitors with ↑/↓ selection
    And x stops the selected monitor and a stops all
