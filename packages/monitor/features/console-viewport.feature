Feature: Monitor console viewport
  Scenario: Terminal diagnostics require disclosure and fit the current terminal
    Given a finished monitor has many diagnostic output lines
    When the monitor console opens in a 24 row terminal
    Then output is hidden until Enter is pressed
    And every frame fits the current terminal rows and columns
    When Enter is pressed and End is pressed
    Then the last diagnostic line is visible
    When the terminal is resized to a tiny window
    Then the console still fits and details remain scrollable

  Scenario: Selection follows identity through completion
    Given two running monitors and the first is selected
    When the first monitor finishes and moves into history
    Then the first monitor remains selected
    And stopping the selected monitor does not stop the second monitor

  Scenario: Every monitor and its detail are reachable
    Given more monitors than the list viewport can display
    When Down is pressed to select the last monitor
    Then that monitor is visible in the list
    When PageDown and End are pressed
    Then details scroll independently of the selection
    When Home is pressed
    Then the details return to the beginning

  Scenario: Fullscreen Pi gives the console its scrolling keys
    Given the console opens in Pi's fullscreen terminal mode
    When PageUp, PageDown, Home, and End are pressed
    Then the focused console receives those keys
    And Pi's transcript viewport does not consume them
    And End reveals the final diagnostic line

  Scenario: Long names keep their state and narrow consoles disclose help
    Given a monitor has a long multilingual description
    When its console renders at 40 and 20 columns
    Then the selected list row still identifies its running state
    And the footer offers help without clipping that action
    When question mark opens help and End is pressed
    Then stop-all and navigation instructions remain reachable
    And closing help restores the selected monitor

  Scenario: Live output refresh belongs only to the open console
    Given a running monitor and an open console
    When the console refresh timer fires
    Then it requests a new frame without polling or messaging the model
    When the console closes
    Then its timer is cleared

  Scenario: Kitty protocol character shortcuts work without release side effects
    Given the terminal encodes printable keys as Kitty CSI-u or xterm modifyOtherKeys input
    When plain or shifted question mark is pressed
    Then help opens
    When x or q is pressed
    Then the selected running monitor stops or the console closes
    And key releases and control-modified character keys do not invoke those shortcuts

  Scenario: Terminal outcomes remain visible and have matching colors
    Given successful, failed, timed out, missing-result and stopped monitors with long names
    When tool results or custom messages render at 20, 40 and 80 columns
    Then the outcome remains visible before the name
    And failed outcomes use error styling while stopped outcomes use neutral styling

  Scenario: Large values have a preview and an explicit full view
    Given a monitor returns a 24 KiB JSON value
    When its transcript details expand
    Then a labelled preview bounds the displayed value without changing structured data
    When v is pressed in the console and End is pressed
    Then the complete value is reachable
    When v is pressed again
    Then the preview returns

  Scenario: Failure evidence precedes configuration
    Given a failed monitor has a long command
    When the console opens in a six-row terminal
    Then its exit code and failure reason are visible before its command

  Scenario: Parallel activity respects the terminal height
    Given twelve monitors are running
    When the activity widget renders
    Then it uses at most three rows and reports the remaining count
    And a six-row terminal uses one summary row

  Scenario: Full values survive session restoration and recent-history eviction
    Given a terminal result is restored or has left the twenty-item recent history
    When its native transcript details expand
    Then complete bounded values are visible without depending on the console
    And already-created components reflect history eviction on their next render

  Scenario: Stopped outcomes use the native theme object
    Given Pi supplies a native Theme instance with prototype methods
    When a stopped outcome is rendered
    Then dim foreground and neutral background render without losing theme methods

  Scenario: Startup expansion prioritizes effective execution settings
    Given an asynchronous monitor starts with default completion and timeout
    When its native startup row expands
    Then it shows pending-at-start and the effective completion, timeout and working directory before the command
    And the full command and explicit success/failure conditions remain available
    And the ID follows the configuration
    And it uses the shared pending style and native expansion hint
    And UI expansion does not change model-facing content or the structured output contract

  Scenario: Startup configuration remains available after restoration
    Given a started result was serialized and the monitor later stopped
    When its startup row expands without original call arguments
    Then its exact command and effective settings come from the stored startup snapshot
    And it identifies a historical pending-at-start state rather than a current running state

  Scenario: Startup configuration keeps significant whitespace
    Given commands, patterns and a working-directory path contain repeated spaces
    When their restored startup row expands
    Then their meaningful spaces and command line breaks remain visible
    And tab and carriage-return controls use explicitly labelled escapes
