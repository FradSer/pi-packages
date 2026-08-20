Feature: Result-contract background monitoring
  The monitor extension runs a shell command in the background, captures its
  output outside the model context, and exposes one machine-verifiable terminal
  result instead of streaming raw progress logs to the agent.

  Background:
    Given the pi-monitor-fradser extension is loaded

  Scenario: Starting a monitor requires a success result contract
    When monitor_start runs with a command, description, and result pattern
    Then a background process is spawned for the command
    And the tool returns a monitor id immediately without blocking
    And the tool result terminates the current agent turn
    And the agent remains idle until the terminal result arrives
    And ordinary stdout and stderr do not wake the agent

  Scenario: A success pattern exposes one compact text result
    Given a monitor is running with a result pattern
    When a line from stdout or stderr matches the result pattern
    Then the matched line and named captures are recorded
    And a named json capture is parsed as structured data when valid
    And the process is stopped
    And the agent is woken exactly once with status "success"
    And the model-facing result uses compact key-value text instead of pretty JSON
    And successful completion does not include noisy diagnostic output

  Scenario: A failure pattern exposes one structured failure
    Given a monitor is running with a failure pattern
    When a line from stdout or stderr matches the failure pattern
    Then the matched line and named captures are recorded
    And the monitor drains trailing output for a brief grace period before finalizing
    And the process is stopped
    And the agent is woken exactly once with status "failure"

  Scenario: A command exits successfully without the contracted result
    Given a monitor is running with a result pattern
    When the command exits with code 0 before the result pattern matches
    Then the agent is woken once with status "result_missing"
    And the expected result pattern is included

  Scenario: A command exits unsuccessfully without a failure match
    Given a monitor is running with a result pattern
    When the command exits with a non-zero code
    Then the agent is woken once with status "failure"
    And the exit code is included

  Scenario: Terminal results include bounded diagnostics without a polling tool
    Given a monitor has captured stdout and stderr
    When the monitor reaches a terminal result
    Then the result includes a bounded tail of source-labelled output
    And no follow-up output-reading tool is available or required

  Scenario: Structured details remain available to extensions
    Given a monitor reaches a terminal result
    When the terminal message is sent to the model
    Then the visible content is compact plain text
    And the message details retain the full structured result object

  Scenario: Captured output is bounded
    Given a monitor is running
    When the command writes oversized lines or a large output burst
    Then individual lines and the retained raw log are truncated to bounded sizes
    And truncation is surfaced in the terminal result

  Scenario: Stopping a monitor manually
    Given a monitor is running
    When monitor_stop runs with its monitor id
    Then the process group receives SIGTERM followed by SIGKILL after the grace period
    And a SIGTERM-resistant descendant still receives SIGKILL escalation after the shell child closes
    And no terminal result notification is sent

  Scenario: Monitor tool surface excludes polling and output-reading tools
    Given the extension tools are registered
    Then monitor_start and monitor_stop tools are available
    And monitor_read and monitor_list tools are not registered
    And the terminal result is the only model notification for a monitor

  Scenario: Session shutdown cleans up all monitors
    Given monitors are running
    When the session shuts down
    Then every background process is killed

  Scenario: Session shutdown completes SIGKILL escalation after the parent exits
    Given a monitor process group contains a SIGTERM-resistant descendant
    When session shutdown sends SIGTERM and the Pi parent is otherwise ready to exit
    Then the parent remains alive through the grace period to send SIGKILL
    And the descendant is no longer alive after the parent exits

  Scenario: Monitor output is surfaced in the UI without entering model context
    Given active or recently finished monitors exist
    When the user opens /monitor
    Then a full-screen console lists the monitors and their bounded recent output
    And x stops the selected active monitor and a stops all active monitors
    And the console renders bounded output without registering an output-reading tool
    And no global input listener is registered

  Scenario: The monitor status is rendered after the native footer
    Given one or more result monitors are waiting
    When the TUI renders the footer
    Then the working directory and token statistics appear first
    And the monitor waiting status appears below the native footer lines
    And the monitor status is not rendered above the editor
