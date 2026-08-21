Feature: Shared pi-kit runtime helpers
  As the pi-packages monorepo
  I want TUI and message helpers shared from one internal runtime package
  So that spinner cadence, theme style callbacks, and message text extraction
  stay identical across agent-teams, btw, memory, recap, vision, and utils

  Scenario: Spinner frames match pi's native loader
    Given a package animates a waiting indicator
    When it imports the shared spinner constants
    Then the frames equal pi's native "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏" braille sequence
    And the shared interval is 120 ms

  Scenario: Theme style language is adapted from any pi theme
    Given a pi theme object with an fg(color, text) function
    When the shared theme style is created
    Then accent, muted, dim, border, success, and error callbacks map to theme fg colors
    And the fg callback passes arbitrary colors through

  Scenario: Compact tool event labels share pi-kit formatting
    Given a monitor tool description
    When a tool event label is formatted
    Then started is `[monitor] started · <description>`
    And terminal events are `[monitor] event · <description>`

  Scenario: Agent task and message labels share pi-kit formatting
    Given an agent task and a teammate name
    When the shared display helpers format them
    Then the task label is "Agent (Agent Alpha - research) · @calc-1 · task-namexxxx"
    And a single incoming message label is "[message] from @calc-1"
    And multiple messages from one teammate are "[2 messages] from @calc-1"
    And outgoing messages can use "[message] to @calc-1"

  Scenario: Plain text is extracted from string message content
    Given message content that is a plain string
    When text content is extracted
    Then the string is returned unchanged

  Scenario: Plain text is extracted from content-block arrays
    Given message content with text blocks mixed with image and thinking blocks
    When text content is extracted
    Then only text block text is joined, in order, with the requested separator
    And non-text blocks contribute nothing

  Scenario: Non-message content yields empty text
    Given content that is neither a string nor an array
    When text content is extracted
    Then an empty string is returned

  Scenario: Model reference is parsed from a provider/model string
    Given a valid "provider/model" string
    When parseModelRef is called
    Then it returns the provider and model parts

  Scenario: Model reference returns undefined for invalid input
    Given an undefined, empty, or malformed value
    When parseModelRef is called
    Then it returns undefined

  Scenario: Model reference is formatted from config
    Given a config with provider and model set
    When modelRef is called
    Then it returns "provider/model"

  Scenario: Model label is formatted from a model object
    Given a model with provider and id
    When modelLabel is called
    Then it returns "provider/id"

  Scenario: Models are sorted by provider/id label
    Given a list of models in arbitrary order
    When sortModels is called
    Then the models are ordered by provider/id

  Scenario: A model is selected from the interactive menu
    Given available models and a current model reference
    When selectModelFromMenu is called with a mock UI
    Then it returns the selected provider/model pair
    And the current model is marked with "current"

  Scenario: Empty model input is returned as undefined
    Given an empty or cancelled input
    When enterModelFromInput is called
    Then it returns undefined

  Scenario: Invalid model input shows an error notification
    Given a malformed model reference
    When enterModelFromInput is called
    Then it notifies with an error and returns undefined

  Scenario: Pi workers inherit their working directory without an unsupported flag
    Given a worker is launched with cwd set on the child process
    When pi-kit builds the non-interactive Pi command
    Then it does not pass the unsupported --cwd option

  Scenario: Pi workers have no wall-clock timeout
    Given a worker is launched from pi-kit
    When the child process is running
    Then the worker API does not accept timeoutMs
    And the child remains alive until it exits or is aborted

  Scenario: pi-kit stays a pure runtime dependency
    Given the pi-kit package manifest
    Then it declares no pi manifest, no dependencies, and no peer dependencies
    And consumer packages declare it under dependencies with the workspace protocol
    And the publish allowlist orders pi-kit before its consumers

  Scenario: Pi CLI resolution accepts only the coding-agent package
    Given the current process entry or installed package is inspected
    When pi-kit resolves a child CLI
    Then an exact @earendil-works/pi-coding-agent package match is accepted
    And an unrelated package whose name merely contains pi is rejected
    And the resolver falls back to a PATH pi executable only after package resolution

  Scenario: Child termination observes close and escalates once
    Given a worker ignores SIGTERM
    When pi-kit terminates the worker
    Then it waits for close during the grace period
    And it escalates to SIGKILL only after the grace period
    And it resolves only after close is observed
