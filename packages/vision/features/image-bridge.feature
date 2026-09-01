Feature: Transparent image reading for text-only models
  The vision extension bridges image input to a configured vision model
  before a text-only main model receives the prompt.

  Scenario: Vision feedback uses the shared TUI notification abstraction
    Given a vision command needs to notify the user
    When it displays information, warnings, or errors
    Then it uses pi-kit's portable notification helper with the requested level

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

  Scenario: Preserve the provider context when image analysis fails
    Given the active model does not support image input
    And the configured vision model fails to analyze an image
    When the user submits a prompt with an image attachment
    Then the text-only model receives the original prompt and image unchanged
    And no image-analysis block or internal provider error is injected into its context

  Scenario: Bound cached analysis across context callbacks
    Given the active model does not support image input
    And the configured vision model can analyze an image
    When duplicate context callbacks transform the same submitted image prompt
    Then the vision model is called once for that prompt
    And completed analysis is retained only for the active prompt
    And pending analyses are cleared when the agent settles

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

  Scenario: Use the required vision working indicator
    Given image analysis is in progress
    When the vision extension shows its working indicator
    Then the indicator cycles through the standard ⠋ ⠙ ⠹ ⠸ ⠼ ⠴ ⠦ ⠧ ⠇ ⠏ frames
    And it does not use circular glyphs

  Scenario: Show active image-reading progress with shared TUI primitives
    Given image analysis is in progress
    When the extension updates its transient status display
    Then it identifies the image count and configured reader through pi-kit's status adapter
    And it uses pi-kit's shared working-indicator adapter with the standard spinner frames and interval
    When image analysis finishes
    Then pi-kit's working-indicator adapter restores Pi's native indicator
    And pi-kit's status adapter hides the vision status entry

  Scenario: Hide the idle vision status entry
    Given the vision bridge is idle
    When the status bar is updated
    Then the configured vision model is not shown
    And the vision status entry is hidden

  Scenario: Bridge images returned from tool results for a text-only model
    Given the active model does not support image input
    And a vision provider and model are configured
    When a tool execution returns an image result
    Then the extension sends the tool image and analysis request to the configured vision model
    And appends the visual analysis to the tool result text
    And removes any non-vision warning notes from the tool result
    And preserves the original image attachment on the tool result

  Scenario: Leave tool result images untouched for a multimodal model
    Given the active model supports image input
    When a tool execution returns an image result
    Then the extension does not call the vision model
    And the tool result continues unchanged
