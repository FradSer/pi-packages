Feature: Compact /memory management menu
  The /memory command exposes a small object-oriented management surface.

  Scenario: Open the compact menu
    Given the project has two safe memory entries
    And automatic learning is enabled
    When the user opens /memory without arguments
    Then the first menu contains only Browse memories, Learning settings, and Recent learning
    And the menu description includes the automatic learning state, model, and entry count

  Scenario: Browse memory metadata and a bounded body
    Given the project has private and shared memory entries
    When the user chooses Browse memories
    Then each entry shows whether it is private or shared
    And choosing an entry displays only its bounded content
    And cancelling the browse flow performs no write

  Scenario: Change learning settings from one settings surface
    Given automatic learning is enabled
    When the user chooses Learning settings
    Then the settings surface offers one model action and one automatic learning toggle
    And advanced phase policy changes are delegated to the existing management handler

  Scenario: Inspect and safely undo recent learning
    Given an applied learning change and a proposed learning change exist
    When the user chooses Recent learning
    Then both records show their status
    And selecting a record shows its bounded detail
    And undo is delegated to the existing management handler only for an applied record
    And a proposed record is never presented as applied

  Scenario: External model labels cannot control the terminal
    Given a configured model label contains terminal control characters
    When the user opens Memory and its Learning settings
    Then every menu title displays a sanitized model label

  Scenario: Opening Memory exposes invalid learning model configuration
    Given memory.json cannot be parsed as a valid learning model configuration
    When the user opens Memory in TUI or headless mode
    Then the model state is shown as configuration invalid rather than unconfigured
    And no learning worker starts
