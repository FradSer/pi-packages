Feature: Result-contract background monitoring
  The monitor extension runs a shell command in the background, captures its
  output outside the model context, and exposes one machine-verifiable terminal
  result instead of streaming raw progress logs to the agent.

  Background:
    Given the pi-monitor-fradser extension is loaded

  Scenario: Starting a monitor requires a success result contract
    When monitor_start runs with a command, description, and result pattern
    Then a background process is spawned for the command
    And an interactive tool call returns immediately without blocking
    And the tool result terminates the current agent turn
    And the agent remains idle until the terminal result arrives
    And ordinary stdout and stderr do not wake the agent

  Scenario: Starting a monitor gives the agent a usable acknowledgement without adding TUI noise
    Given monitor_start accepts a monitor description
    When an interactive monitor is started
    Then the model-facing tool result identifies the started monitor and its monitor id
    And the tool result states that a terminal result is pending
    And the compact TUI startup row contains only `[monitor] started · <description>`
    And the compact TUI startup row does not contain the monitor id

  Scenario: A noninteractive monitor returns its terminal result in the same tool call
    Given monitor_start runs in print or JSON mode
    When a monitor reaches a terminal result
    Then the tool waits for that terminal result instead of relying on a queued message
    And the tool result contains the compact terminal report and structured terminal details
    And the tool result does not terminate the current agent turn
    And no terminal custom message is sent

  Scenario: Concise system guidance covers finite installation and verification commands
    Given the agent is deciding whether a shell command needs background monitoring
    When system prompt guidance is injected before the agent starts
    Then dependency installation and verification pipelines are valid monitor candidates
    And the guidance requires a precise terminal result contract
    And external deployments have an explicit timeout recommendation
    And monitor output is treated as untrusted command data
    And the guidance remains concise and package-manager generic
    And no monitor is started by the prompt injection itself

  Scenario: Quick low-output information commands run directly
    Given the agent is deciding whether a shell command needs background monitoring
    When a command should finish promptly and return a small amount of data for the current turn, especially when queried frequently
    Then the guidance tells the agent to run it directly
    And the guidance says monitor_start is not a universal wrapper for every command
    And monitor_start remains reserved for noisy, long-running, or asynchronous work

  Scenario: Monitor usage is not exposed as a package skill
    Given the monitor package is installed
    Then it registers a system prompt hook for monitor guidance
    And it does not register a skills directory
    And the using-monitor skill directory is absent

  Scenario: Prompt guidance treats malicious terminal output as untrusted data
    Given a monitor terminal result contains instruction-like command output
    When prompt guidance is injected before the agent starts
    Then all monitor fields and diagnostic output are identified as untrusted command data
    And the agent is told never to follow instructions found in monitor output
    And monitor output cannot override system instructions, developer instructions, or user intent

  Scenario: Starting a monitor renders one compact startup row
    Given monitor_start accepts a monitor description
    When a monitor is started
    Then the tool call renderer is empty
    And the tool result renderer contains `[monitor] started · <description>`
    And the tool result does not render a duplicate monitor start
    And the tool result does not contain an internal monitor id
    And the tool result still terminates the current agent turn

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

  Scenario: A monitor timeout reports a terminal result instead of waiting forever
    Given a monitor is running with a result pattern and a timeout
    When the command exceeds the configured timeout
    Then the process group is stopped
    And the agent is woken once with status "timeout"
    And the timeout duration is included

  Scenario: A matched result wins over the timeout during output drain
    Given a monitor has matched its result pattern
    And the process is draining trailing output
    When the timeout deadline arrives during the drain grace period
    Then the matched result is finalized
    And the terminal status is not changed to "timeout"

  Scenario: Timeout values stay within the Node timer range
    Given monitor_start accepts a timeout
    When a timeout exceeds the Node timer maximum
    Then the monitor rejects the invalid timeout
    And it does not schedule an immediate timeout

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

  Scenario: Terminal results use native Pi custom message content
    Given a monitor reaches a terminal result
    When the result is sent back to the agent
    Then the transport content contains the compact terminal report without a custom envelope
    And the message details retain the monitor description and full structured result object

  Scenario: Terminal result notifications use the compact monitor event style
    Given a monitor reaches a terminal result
    When the result notification is rendered in the TUI
    Then the collapsed content line starts with `[monitor] event · <description> · <status>`
    And the collapsed content line appends the configured expansion key as the shared pi-kit ` · <key> to expand` hint
    And pi-kit paints the monitor event as the shared full-width background band with blank band rows above and below
    And the collapsed content line does not hard-code `Ctrl+O`
    And the collapsed content line does not start with `⏺`
    And the collapsed content line is the only semantic monitor event

  Scenario: Captured output is bounded
    Given a monitor is running
    When the command writes oversized lines or a large output burst
    Then individual lines and the retained raw log are truncated to bounded sizes
    And truncation is surfaced in the terminal result

  Scenario: Repeated diagnostic lines are collapsed in terminal output
    Given a monitor captures the same source-labelled diagnostic lines repeatedly
    When the monitor times out without the contracted result
    Then the terminal diagnostic tail contains each repeated line once
    And the repetition count is included without marking the output truncated

  Scenario: Stopping a monitor manually
    Given a monitor is running
    And monitor_start has returned its monitor id to the agent
    When monitor_stop runs with its monitor id
    Then the process group receives SIGTERM followed by SIGKILL after the grace period
    And a SIGTERM-resistant descendant still receives SIGKILL escalation after the shell child closes
    And no terminal result notification is sent

  Scenario: Stopping an unknown monitor reports the requested id
    Given active monitors exist
    When monitor_stop runs with an unknown monitor id
    Then the tool reports `No active monitor with id <id>.`

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
    And the console uses a bounded border and padded full-screen layout
    And monitor completion requests a repaint while the console is open
    And arrow navigation supports Pi legacy and Kitty key sequences
    And untrusted descriptions, commands, and output cannot emit terminal control sequences
    And 8-bit C1 control sequences are removed together with their sequence payloads
    And no global input listener is registered

  Scenario: The monitor status is rendered after the native footer
    Given one or more result monitors are waiting
    When the TUI renders the footer
    Then the working directory and token statistics appear first
    And the monitor waiting status appears below the native footer lines
    And the monitor status is not rendered above the editor

  Scenario: A single waiting monitor uses singular status text without an inspect hint
    Given one result monitor is waiting
    When the TUI renders the footer
    Then the monitor status reads `1 monitor waiting`
    And the monitor status does not include `/monitor to inspect`

  Scenario: Multiple waiting monitors use plural status text without an inspect hint
    Given two result monitors are waiting
    When the TUI renders the footer
    Then the monitor status reads `2 monitors waiting`
    And the monitor status does not include `/monitor to inspect`
