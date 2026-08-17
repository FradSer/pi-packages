Feature: Session Recap
  The recap package displays a concise, scannable summary of the current session
  above the TUI input box (aboveEditor widget), inspired by Claude Code's recap.
  When installed, it automatically captures completed turns and shows the latest
  recap by default. Running /recap opens an interactive management TUI (similar
  to @packages/memory/ and @packages/vision/) to manage recap generation,
  select custom models, and configure language preferences.

  Background:
    Given the @fradser/pi-recap package is installed

  Scenario: Recap widget is displayed above the editor by default
    Given an active session in TUI mode
    When a turn completes with a user request and assistant response
    Then a concise recap is generated
    And it is displayed above the editor with the format "※ Recap: <summary>"

  Scenario: Recap is informative and scannable
    Given a raw model summary
    When cleaned and formatted
    Then the recap text is a single line with specific action, target, and outcome
    And quotes, markdown wrappers, and redundant prefixes are stripped

  Scenario: Generated recap is persisted to the session
    Given a newly generated recap for the current exchange
    When generation completes
    Then the recap is persisted as a session entry via appendEntry
    And synced to the directory session registry

  Scenario: Existing session restores persisted recap on startup across restarts
    Given a session with a persisted recap in session branch history
    When session_start fires on restart
    Then the latest persisted recap is restored directly to the widget
    And no new recap generation is triggered

  Scenario: Existing session without saved recap computes initial recap on startup
    Given a session with existing messages in history and no saved recap
    When session_start fires
    Then the last exchange is extracted and recap generation is performed

  Scenario: /recap opens an interactive management menu
    Given an active session in TUI mode
    When the user runs /recap
    Then an interactive select menu opens displaying the current recap, language, and management options

  Scenario: Model selection supports custom provider and model overrides
    Given the recap management menu
    When the user selects a custom recap model
    Then the preference is persisted in recap.json
    And subsequent recap generations use the configured model

  Scenario: Language selection allows specifying target generation language
    Given the recap management menu
    When the user chooses "Chinese (中文)" or "English"
    Then the target language preference is persisted
    And prompt instructions enforce outputting in that specified language

  Scenario: Recap maintains context continuity using previous recap and last exchange
    Given a session with an existing recap "Fixing authentication token validation"
    When a new turn completes with "Add unit tests for the token validator"
    Then the recap generator prompt includes the previous recap and the latest exchange
    And produces an updated progressive summary

  Scenario: Recap shows a generation marker while refreshing
    Given an active session in TUI mode
    When recap generation starts
    Then the widget shows an animated "⠙ Recapping..." status line
    And the recap content remains on its own "※ Recap:" line
    And the previous recap remains visible until the new recap is ready
    When recap generation finishes
    Then the generation marker is replaced by the new recap

  Scenario: Recap marker aligns with the native working spinner
    Given the recap widget is displayed above the editor
    When the recap content is rendered
    Then the recap marker starts in the same visual column as the native working spinner
    And continuation lines align with the first recap character rather than the marker

  Scenario: Existing recap prevents redundant startup generation
    Given a saved recap exists for the current session
    When session_start fires
    Then the saved recap is displayed without starting another generation

  Scenario: Recap generation requests are deduplicated and cancellable
    Given recap generation is already running
    When a request for the same exchange starts
    Then it reuses the existing request
    When a request for a newer exchange starts
    Then the previous request is cancelled
    And the newer result cannot be overwritten by the previous result

  Scenario: Recap generation times out safely
    Given recap generation does not complete before its timeout
    When the timeout is reached
    Then the request is cancelled
    And the previous recap remains visible

  Scenario: Recap ignores thinking-only provider output
    Given a provider response contains thinking but no text
    When the recap response is extracted
    Then no recap is produced

  Scenario: Recap skips unchanged persistence
    Given the generated recap matches the displayed recap
    When generation finishes
    Then the recap file is not rewritten
    And the widget is not refreshed for a content change

  Scenario: Recap runs in-process without blocking interaction
    When an agent turn settles
    Then the recap generation runs asynchronously using the model registry
    And the user can continue typing immediately
