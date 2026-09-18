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
    And the running monitor keeps an above-editor activity row visible while the agent is idle
    And ordinary stdout and stderr do not wake the agent

  Scenario: Tool guidance keeps the description, the sentinel, and the pattern in separate fields
    Given monitor_start exposes parameter descriptions and prompt guidelines to the agent
    When the agent prepares a contracted background command
    Then the guidance places the success sentinel in the command
    And the guidance places the matching regular expression in result_pattern
    And the guidance keeps the failure regular expression in failure_pattern
    And the guidance keeps the description a short human label
    And the guidance forbids restating the command or the result pattern in the description
    And the guidance does not tell the agent to declare the terminal result before starting

  Scenario: Bare PCRE case-insensitive flags receive an actionable validation error
    Given monitor_start receives a result or failure pattern beginning with bare `(?i)`
    When JavaScript validates the regular expression
    Then monitor_start rejects the pattern without changing its matching behavior
    And the error explains that JavaScript RegExp does not support bare `(?i)` flags
    And the error recommends scoped `(?i:...)` syntax for the case-insensitive group or explicit case alternatives

  Scenario: Literal inline-flag text remains valid regular expression syntax
    Given a result pattern contains `(?i)` inside a character class or as escaped literal text
    When monitor_start validates the regular expression
    Then the pattern retains its native JavaScript RegExp behavior
    And monitor_start does not apply the bare PCRE flag diagnostic

  Scenario: Starting a monitor gives the agent a usable acknowledgement without adding TUI noise
    Given monitor_start accepts a monitor description
    When an interactive monitor is started
    Then the model-facing tool result identifies the started monitor and its monitor id
    And the tool result states that a terminal result is pending
    And the compact TUI startup row contains only `[monitor] started · <description>`
    And the compact TUI startup row does not contain the monitor id

  Scenario: The monitor description is optional and derived from the command
    Given monitor_start accepts a command and a result pattern without a description
    When the agent omits the description
    Then the started monitor derives a short human label from the command
    And the derived label collapses whitespace onto one line, drops a leading shell wrapper such as `sh -c`, and truncates to a bounded width
    And the model-facing acknowledgement and the compact startup row both use the derived label
    And an explicit description still overrides the derived label

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

  Scenario: Monitor TUI messages use the shared Pi-kit renderers
    Given the monitor package renders a tool result, terminal message, console, or notification
    When a monitor lifecycle event becomes visible in Pi
    Then tool and custom-message rows use Pi-kit's lifecycle renderer
    And the console uses Pi-kit's shared panel renderer
    And command feedback uses Pi-kit's notification adapter

  Scenario: Starting a monitor renders one shared lifecycle row
    Given monitor_start accepts a monitor description
    When a monitor is started
    Then the tool call renderer is empty
    And the tool result renders `[monitor] started · <description>` through the bound pi-kit lifecycle renderer
    And the startup row paints the shared background band with the configured expansion hint
    And expanding the row shows the command, the success contract, and the monitor id as `label · value` fields
    And an optional failure pattern is shown as its own `label · value` field
    And the monitor id stays visible because monitor_stop needs it
    And the tool result does not render a duplicate monitor start
    And the tool result still terminates the current agent turn

  Scenario: A success pattern exposes one compact text result
    Given a monitor is running with a result pattern
    When a line from stdout or stderr matches the result pattern
    Then the matched line and named captures are recorded
    And a named json capture is parsed as structured data when valid
    And optional named capture groups that did not participate are omitted without crashing the Pi session
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
    And the expanded body lists status, elapsed, result, and output as `label · value` fields

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

  Scenario: Monitor stop tool is progressively disclosed while monitors run
    Given monitor_start and monitor_stop tools are registered
    When the extension initializes with no running monitors
    Then monitor_start is active
    And monitor_stop is inactive
    When one or more monitors start
    Then monitor_stop becomes active without removing monitor_start
    When the final monitor stops or reaches any terminal result
    Then monitor_stop is inactive
    And monitor_start remains active
    And session shutdown leaves monitor_stop inactive

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

  Scenario: Monitor notifications use the shared Pi-kit notification adapter
    Given a monitor command reports no active or recent monitors
    When the extension notifies the user
    Then it delegates notification sanitization and delivery to pi-kit

  Scenario: Monitor activity uses the shared Pi-kit live activity widget
    Given a monitor is running
    When the extension refreshes its monitor activity
    Then it mounts one above-editor activity row per running monitor through pi-kit's live activity widget
    And the row uses Pi's native spinner cadence with the `monitor` identity and the monitor description as activity
    And it clears the activity row when no monitor is running
    And it does not write a transient footer status entry

  Scenario: The monitor activity is rendered above the editor instead of below the input
    Given one or more result monitors are running
    When the TUI renders the input area
    Then the monitor activity appears above the editor as a spinner row
    And nothing about running monitors appears in the footer below the directory and usage lines

  Scenario: Every running monitor keeps its own activity row
    Given two result monitors are running
    When the TUI renders the monitor activity
    Then two above-editor activity rows appear, one per running monitor
    And each row carries that monitor's description as its activity
    And a finished or stopped monitor's row is removed without disturbing the remaining rows

  Scenario: The monitor extension does not intercept bash tool calls
    Given the monitor extension is loaded
    When the model calls the bash tool with a long-running command or a high timeout
    Then the monitor extension does not register a bash tool-call guardrail
    And the native bash tool remains responsible for synchronous execution

  Scenario: Monitor guidance recommends monitor_start without changing bash behavior
    Given the monitor extension is loaded
    When the agent decides whether a shell command needs background monitoring
    Then the system guidance recommends monitor_start for noisy, long-running, or asynchronous work
    And the system guidance does not require a special command suffix
    And the system guidance does not claim that synchronous bash is blocked
