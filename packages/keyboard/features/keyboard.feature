Feature: Pi Keyboard Lighting Indicator
  As a Pi developer
  I want my VIA/QMK keyboard lighting to dynamically reflect Pi's internal states
  So that I have ambient physical awareness of agent status without looking at the terminal

  Background:
    Given a VIA-compatible keyboard with Raw-HID support
    And the keyboard has RGB lighting configuration

  Scenario: Pi transitions to idle state with white breathing light
    Given Pi is in session startup or waiting for new user input
    When the keyboard state machine updates to "idle"
    Then the keyboard lighting is set to white color
    And the effect mode is set to breathing
    And the update is applied immediately in memory without saving to EEPROM

  Scenario: Pi transitions to unread chat state with green breathing light
    Given the agent has finished generating a response
    And the user has not yet submitted new input
    When the agent settles with a completed message
    Then the keyboard state machine updates to "unread_chat"
    And the keyboard lighting is set to green color
    And the effect mode is set to breathing
    And the update is applied with --no-save in memory

  Scenario: Pi transitions to thinking state with blue breathing light
    Given a user has submitted a prompt or the agent is executing a turn
    When the agent starts thinking or executing tools
    Then the keyboard state machine updates to "thinking"
    And the keyboard lighting is set to blue color
    And the effect mode is set to breathing
    And the update is applied with --no-save in memory

  Scenario: Pi transitions to need approval state with yellow blinking light
    Given a tool call requires user confirmation or approval
    When an interactive gate or question is prompted
    Then the keyboard state machine updates to "need_approval"
    And the keyboard lighting is set to yellow color
    And the effect mode is set to blinking alert
    And the update is applied with --no-save in memory

  Scenario: Pi transitions to error state with red blinking light
    Given an agent execution error, API failure, or turn error occurs
    When a fatal error event is captured
    Then the keyboard state machine updates to "error"
    And the keyboard lighting is set to red color
    And the effect mode is set to blinking alert
    And the update is applied with --no-save in memory

  Scenario: Non-fatal tool errors do not trigger red blinking light
    Given the agent executes a bash command or test that returns a non-zero exit code
    When the tool result arrives during ongoing turn reasoning
    Then the keyboard lighting remains in "thinking" blue breathing state
    And it does not trigger the red error alert

  Scenario: User submits input and clears unread chat status
    Given the keyboard is currently displaying unread chat state
    When the user submits a new prompt in the conversation
    Then the unread status is cleared
    And the keyboard state machine transitions to "thinking"

  Scenario: Target lighting zone selection
    Given the user configures the target zone
    When the zone is set to "matrix"
    Then only channel 3 (key backlight) is updated
    When the zone is set to "underglow"
    Then only channel 2 (side strip) is updated
    When the zone is set to "all"
    Then both channel 2 and channel 3 are updated

  Scenario: In-memory updates without EEPROM wear
    Given any state transition is dispatched to hardware
    When the HID command is executed
    Then it operates strictly in RAM using no-save mode without sending save command 0x09

  Scenario: State change deduplication prevents redundant HID writes
    Given the keyboard is already displaying "thinking" state
    When another turn or tool call event occurs while still "thinking"
    Then redundant hardware HID commands are skipped

  Scenario: Keyboard disconnection handling
    Given the keyboard is unplugged or unavailable
    When a state transition occurs
    Then the driver fails gracefully without throwing unhandled exceptions or crashing Pi

  Scenario: /keyboard command allows manual state testing and toggle
    Given the /keyboard command is executed
    When the user toggles lighting to "off"
    Then all keyboard lighting updates are disabled
    When the user runs "/keyboard test thinking"
    Then the keyboard lighting displays the blue thinking state
