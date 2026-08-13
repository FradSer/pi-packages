Feature: /effort thinking-level command
  The utils package exposes a pi-native /effort command that sets the session
  thinking (reasoning effort) level. With no argument it opens a menu of the
  levels the current model supports; with an argument it sets the level
  directly (with short aliases). The manifest registers it as an extension.

  Background:
    Given the @fradser/utils package is installed

  Scenario: Manifest registers the extensions directory
    Given the package manifest
    When inspected
    Then its pi section exposes ./extensions
    And the extension file ships beside the skills

  Scenario: /effort with no argument opens a level menu
    Given a TUI session with the current model
    When the user runs /effort
    Then a menu of supported thinking levels is offered
    And the current level is marked in the menu
    And selecting a level calls setThinkingLevel with it

  Scenario: /effort <level> sets the level directly
    When the user runs /effort max
    Then setThinkingLevel("max") is called
    And a confirmation is shown

  Scenario: Short aliases map to canonical levels
    Given the aliases min, med, xh, none, and 0
    When the user runs /effort min
    Then setThinkingLevel("minimal") is called

  Scenario: Unknown levels are rejected with a hint
    When the user runs /effort turbo
    Then no level is set
    And an error lists the valid levels

  Scenario: Model capability narrows the menu
    Given the current model has reasoning disabled
    When the user runs /effort
    Then only "off" is offered

  Scenario: Non-TUI sessions get a plain notification
    Given a session without UI
    When the user runs /effort
    Then the current level is reported instead of a menu
