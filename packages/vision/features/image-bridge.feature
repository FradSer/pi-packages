Feature: Transparent image reading for text-only models
  The vision extension bridges image input to a configured vision model
  before a text-only main model receives the prompt.

  Scenario: Read attached images before a text-only model runs
    Given the active model does not support image input
    And a vision provider and model are configured
    When the user submits a prompt with one or more images
    Then the extension sends the images and prompt to the configured vision model
    And transforms the prompt with the returned visual context
    And removes the original images before the main model receives the prompt

  Scenario: Leave images untouched for a multimodal main model
    Given the active model supports image input
    When the user submits a prompt with images
    Then the extension does not call the vision model
    And the original prompt and images continue unchanged

  Scenario: Fail closed when the bridge is not configured
    Given the active model does not support image input
    And no vision model is configured
    When the user submits a prompt with images
    Then the extension does not send the image to the text-only model
    And tells the user how to configure a vision model

  Scenario: Select the vision model from the command
    When the user runs "/vision model provider/model"
    Then the provider and model are persisted in the vision configuration
    And subsequent image prompts use that model

  Scenario: Manage the bridge from the TUI menu
    Given the user runs "/vision" in an interactive Pi session
    When the vision menu opens
    Then it shows the current enabled state and configured model
    And offers model selection, manual model entry, enable or disable, configuration details, and reset

  Scenario: Select a configured vision model from the TUI
    Given the model registry contains image-capable models
    When the user chooses model selection from the vision menu
    Then the menu offers only models from the current Pi model scope that declare image input support
    And selecting one persists its provider and model

  Scenario: Use all available models when Pi has no explicit model scope
    Given Pi has no explicit model scope
    When the user chooses model selection from the vision menu
    Then the menu uses Pi's currently available model list

  Scenario: Hide the unconfigured status entry
    Given the vision bridge is enabled without a configured reader model
    When the status bar is updated
    Then the vision status entry is hidden
