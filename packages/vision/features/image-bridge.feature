Feature: Transparent image reading for text-only models
  The vision extension bridges image input to a configured vision model
  before a text-only main model receives the prompt.

  Scenario: Read attached images before a text-only model runs
    Given the active model does not support image input
    And a vision provider and model are configured
    When the user submits a prompt with one or more image attachments
    Then the extension sends the images and a cleaned analysis request to the configured vision model
    And preserves the complete original prompt and image attachment as the user message
    And adds the returned visual analysis only to a transient provider context after the original input
    And does not replace, remove, rewrite, or add an internal message to the user's session history

  Scenario: Intercept an image pasted into the Pi TUI
    Given Pi saved a pasted clipboard image to a temporary image file
    And inserted the image file path into the input editor
    And the active model does not support image input
    When the user submits surrounding text and the pasted image path
    Then the extension reads the image file before the main model runs
    And sends the image and surrounding text to the configured vision model
    And removes the image path from the vision analysis request
    And the user message preserves the original image path
    And the visual analysis is added only to the transient provider context

  Scenario: Leave images untouched for a multimodal main model
    Given the active model supports image input
    When the user submits a prompt with images
    Then the extension does not call the vision model
    And the original prompt and images continue unchanged

  Scenario: Fail closed when the bridge is not configured
    Given the active model does not support image input
    And no vision model is configured
    When the user submits a prompt with images
    Then the extension preserves the original user message
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

  Scenario: Hide the idle vision status entry
    Given the vision bridge is idle
    When the status bar is updated
    Then the configured vision model is not shown
    And the vision status entry is hidden
