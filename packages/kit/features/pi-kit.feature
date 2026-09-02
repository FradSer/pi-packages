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

  Scenario: Lifecycle titles share the spec formatting across tools
    Given a lifecycle tool and subject
    When a title is formatted from a ToolLifecycleSpec
    Then started rows are `[monitor] <subject>`
    And terminal events are `[monitor] <subject>`
    And semantic verbs ride the optional label as `[sessions] listed · <subject>` or `[context] gathered · <subject>`

  Scenario: Lifecycle tool renderers provide the shared started and event row contract
    Given a tool renderer configured with pi-kit lifecycle primitives
    When the renderer handles a started result
    Then it owns an empty call slot and one width-bounded `[tool] started · <subject>` row
    And any collapsed lifecycle row with details reserves width for and preserves the configured expand hint
    And pi-kit paints every successful row block as a full-width customMessageBg band with one blank band row above and below
    And a truncated row's ellipsis and padding keep the same band background, because pi-kit re-applies the background after any full SGR reset
    And the title prefix is label-colored and bold while @teammate names get a stable per-agent accent color from pi-kit's palette
    And collapsed teammate-message rows use the same band via renderAgentMessageBand as `[message] from @name · <key> to expand`
    And class-based theme methods retain their receiver when pi-kit applies the background band
    And a long title truncates before the expand hint instead of truncating the hint
    And when it handles an expanded result it reveals at most 50 detail lines by default
    And a lifecycle spec with detailLimit="all" preserves every expanded detail line
    And an error result is rendered as one plain error row without a lifecycle label
    And a static result renderer keeps model-only result text out of the expandable user-facing row
    And a lifecycle row can show a compact multi-line summary while remaining expandable

  Scenario: Overlay panels use the shared frame layout
    Given an overlay has a header, body lines, and a footer
    When it uses renderPiPanel
    Then the panel has shared full-width border, padded header and footer lines
    And every emitted line is width-bounded by the supplied ANSI-aware fit helper

  Scenario: Passive console widgets use the shared row layout
    Given a package displays a one-line status widget
    When it uses renderPiWidgetRow
    Then the row has the native one-space leading alignment and is width-bounded

  Scenario: Custom transcript messages use the standard lifecycle renderer
    Given a package sends a custom transcript message with a lifecycle spec
    When it creates the reusable pi-kit message renderer
    Then Pi receives a width-aware component using renderToolLifecycle
    And the renderer carries the shared expand hint and lifecycle band unchanged

  Scenario: Custom native tools use the standard lifecycle result renderer
    Given a native tool result with text content and optional structured details
    When it creates a reusable pi-kit tool lifecycle renderer
    Then a successful result renders the shared lifecycle band
    And an error delegates its plain sanitized error row to the host renderer

  Scenario: Notifications use the shared portable UI abstraction
    Given a package needs to notify through ctx.ui
    When it calls notifyPi
    Then the message is sanitized and forwarded with the requested notification level

  Scenario: Passive extension widgets use Pi-kit's shared rendering helpers
    Given a package registers a passive widget with Pi
    When it renders visible widget content
    Then its rows use Pi-kit's shared widget-row renderer
    And any multi-line panel uses Pi-kit's shared panel renderer

  Scenario: Transient status and working indicator use shared Pi-kit adapters
    Given a package needs to show or clear a transient TUI status
    When it uses pi-kit's status adapter
    Then the status key and visible text are sanitized before delivery to Pi
    And clearing the status forwards an undefined value
    When it starts or clears Pi's working indicator through pi-kit
    Then the standard shared spinner frames and cadence are used for start
    And clearing restores Pi's native working indicator

  Scenario: Agent task and message prefixes share pi-kit formatting
    Given an agent task and message direction
    When the shared display helpers format them
    Then a single incoming message prefix is "[message] from "
    And multiple messages from one teammate are "[2 messages] from "
    And outgoing messages use "[message] to "
    And the task name carries no width cap; fixed panels apply their own explicit width bound

  Scenario: Scroll window bounds clamp within available content
    Given a list of lines and a viewport height
    When computeScrollWindow calculates the visible slice
    Then the start and end indices slice the content within bounds
    And scrolling past the end is clamped to the maximum scroll offset

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

  Scenario: Display text is sanitized for terminal output
    Given untrusted registry values containing ANSI, OSC, and control characters
    When safeDisplayText sanitizes them
    Then escape sequences are stripped and only printable text remains

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

  Scenario: Model search text leads with the provider-prefixed label
    Given a model with provider, id, and display name
    When modelSearchText formats it
    Then the text starts with "provider/id" and includes the display name
    And a nameless model still produces searchable text without a trailing separator

  Scenario: A search picker filters models by query and resets the selection
    Given a picker over sorted models with an injected filter
    When characters are typed into the query
    Then results contain only models whose search text matches
    And the selection points at the first result

  Scenario: A search picker restores previous results on backspace
    Given a picker narrowed by a query
    When the last query character is removed
    Then results widen back toward the full list
    And clearing the query restores every model in original order

  Scenario: Search picker navigation clamps within filtered results
    Given a picker with several filtered results
    When down is pressed past the end or up before the start
    Then the selection stays within bounds
    And an empty result list has no selection

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
    And the publish allowlist includes every package with a pending release
    And every package named by a pending Changeset resolves to a workspace manifest

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
