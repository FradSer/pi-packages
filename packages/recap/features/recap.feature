Feature: Session Recap
  The recap package displays a concise, scannable summary of the current session
  above the TUI input box (aboveEditor widget), inspired by Claude Code's recap.
  When installed, it automatically captures completed turns and shows the latest
  recap by default. Running /recap opens an interactive management TUI (similar
  to @packages/memory/ and @packages/vision/) to manage recap generation,
  select custom models, and configure language preferences.

  Background:
    Given the pi-recap-fradser package is installed

  Scenario: Recap feedback uses the shared TUI notification abstraction
    Given a recap command needs to notify the user
    When it displays information, warnings, or errors
    Then it uses pi-kit's portable notification helper with the requested level

  Scenario: Recap widget uses pi-kit's shared live activity and row renderers
    Given an active session in TUI mode displays a recap
    When its status or recap content is rendered
    Then in-progress recap activity uses pi-kit's live activity widget
    And every completed recap row uses pi-kit's shared widget-row renderer

  Scenario: Persisted recap entries stay out of the transcript
    Given a persisted recap entry exists in the session branch
    When Pi renders the session transcript
    Then the recap extension registers no entry renderer
    And the recap entry adds no TUI message row
    And the recap appears only above the editor as "✦ Recap: <summary>"

  Scenario: Recap widget is displayed above the editor by default
    Given an active session in TUI mode
    When a turn completes with a user request and assistant response
    Then a concise recap is generated
    And it is displayed above the editor with the format "✦ Recap: <summary>"

  Scenario: A complete recap row is never marked as truncated
    Given an active session in TUI mode
    And a recap whose wrapped lines fill the available width
    When the recap widget renders it
    Then every rendered row fits within the terminal width
    And no row carries a truncation marker for content that was never dropped
    And the rendered rows still carry the whole recap

  Scenario: First user prompt starts an immediate in-progress recap
    Given a new TUI session with no previous recap
    When the user submits their first prompt
    Then recap generation starts before the agent turn settles
    And the widget tells the user that work is being recapped
    And the completed turn can later refresh the recap with its outcome
    And settling the turn is not delayed by the in-progress recap

  Scenario: In-progress recap does not claim requested work is complete
    Given a new TUI session with no previous recap
    When the first prompt is being recapped before the assistant responds
    Then the recap prompt identifies the work as starting or planned
    And it forbids claiming actions, files, connections, or results that are not evidenced

  Scenario: Automatic recapping is withheld from reasoning models by default
    Given automatic recapping has no explicit preference stored
    And the recap model is the session's own reasoning model, which the user never chose for recaps
    When a turn settles
    Then no recap request is sent for that turn
    And manual generation and the restored recap line stay available
    When the user runs "/recap auto" or chooses a recap model
    Then automatic recapping resumes
    And the preference is persisted as an explicit choice

  Scenario: The cost policy is reported instead of silently skipping turns
    Given automatic recapping is suppressed by the cost policy
    When the user opens the recap menu or the headless configuration summary
    Then the auto-recap state is shown as off with the reason
    And the option to enable auto-recap is offered

  Scenario: Startup recap for a session that has none is not withheld
    Given an existing TUI session with history and no saved recap
    And automatic recapping is suppressed by the cost policy
    When session_start fires
    Then the one startup recap is still computed

  Scenario: Recap is informative and scannable
    Given a raw model summary
    When cleaned and formatted
    Then the recap text is a single line with specific action, target, and outcome
    And quotes, markdown wrappers, and redundant prefixes are stripped

  Scenario: Empty or meaningless recap output is retried
    Given the recap model returns no text, only a generic action plus a bare identifier, or only a bare label
    When a recap is generated
    Then the output is rejected as uninformative in every configured language
    And the model is asked once more for a specific recap
    And only an informative retry can be displayed or persisted

  Scenario: The recap prompt rules stay bounded
    Given a recap is generated
    When its prompt is built
    Then each rule states one distinct requirement
    And the rule list stays short enough that no rule outweighs the rest

  Scenario: The recap length cap never corrupts the recap
    Given a recap longer than the length cap that contains astral characters or an inline code span
    When it is truncated for display
    Then no character is split into a lone surrogate
    And an inline code span opened by the cut is dropped instead of left unbalanced

  Scenario: Recap models have enough output budget to finish a summary
    Given a recap model uses part of its completion budget for reasoning
    When recap generation requests a completion
    Then the output budget is large enough for the model to also return the recap text

  Scenario: Provider failures are not retried as output-quality failures
    Given the recap provider rejects the completion request
    When recap generation handles the failure
    Then generation stops after the first provider call
    And no immediate duplicate request is sent

  Scenario: Manual recap reports the actual failure reason
    Given the user requests a recap manually
    When no complete exchange exists or the configured model fails
    Then the warning distinguishes missing conversation history from generation failure

  Scenario: Recap reflects only evidenced progress
    Given a user request with a plan and desired outcome but no assistant result
    When the recap prompt is built
    Then the request is treated as planned work rather than completed work
    And unsupported actions, files, connections, and results are forbidden

  Scenario: Recap pairs the latest complete answer with its preceding user request
    Given the branch contains "Q1", a complete answer "A1", and a newer request "Q2"
    When the latest recap exchange is extracted
    Then it uses "Q1" with "A1"
    And it does not pair "Q2" with the older answer

  Scenario: Interrupted or failed answers are excluded from recap exchanges
    Given a newer request has an aborted, failed, or otherwise incomplete assistant message
    When the latest recap exchange is extracted
    Then the incomplete request is omitted
    And the last complete valid answer remains paired with its own preceding request

  Scenario: Recap keeps the newest complete answer for one user request
    Given one user request has a complete answer, a custom follow-up entry, and another complete answer
    When the latest recap exchange is extracted
    Then it uses the newest complete answer for that user request

  Scenario: Generated recap is persisted to the session
    Given a newly generated recap for the current exchange
    When generation completes
    Then the recap is persisted as a session entry via appendEntry
    And synced to the directory session registry

  Scenario: Directory recap sync uses canonical session ownership
    Given two project directories whose names differ only by slash versus hyphen
    When recap state is read or synchronized
    Then each registry record is addressed by its canonical hashed directory identity
    And a record with a different canonical cwd is ignored
    And the registry path resolves the same way for every package that shares it
    And the recap field is the only one the recap package writes

  Scenario: Existing session restores persisted recap on startup across restarts
    Given a session with a persisted recap in session branch history
    When session_start fires on restart
    Then the latest persisted recap is restored directly to the widget
    And no new recap generation is triggered

  Scenario: Session replacement cancels a pending first-prompt recap
    Given the first-prompt recap is still generating in a TUI session
    When a replacement session starts
    Then the pending recap request is aborted
    And its result cannot update the replacement session

  Scenario: Existing session without saved recap computes initial recap on startup
    Given a session with existing messages in history and no saved recap
    When session_start fires
    Then the last exchange is extracted and recap generation is performed

  Scenario: /recap opens an interactive management menu
    Given an active session in TUI mode
    When the user runs /recap
    Then an interactive select menu opens showing the recap state, language, and management options
    And the menu does not repeat the current recap text

  Scenario: Generate recap now bypasses same-exchange deduplication
    Given the current exchange already has a displayed recap
    When the user selects "Generate recap now" from the recap menu
    Then recap generation calls the configured model again
    And the displayed recap is replaced with the refreshed result

  Scenario: Model selection supports custom provider and model overrides
    Given the recap management menu offering one "Select recap model" option
    When the user selects a custom recap model
    Then the preference is persisted in recap.json
    And subsequent recap generations use the configured model
    When the user dismisses the model picker without selecting a model
    Then the stored model override is cleared
    And recap generation falls back to the session default model

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

  Scenario: Regeneration replaces the recap line with a generation marker
    Given an active session in TUI mode with a visible recap
    When recap generation starts
    Then the above-editor line shows only an animated "⠹ Recapping..."
    And the generation marker carries no "· Working..." activity suffix
    And the "✦ Recap:" line is hidden while generation is running
    When recap generation finishes
    Then the generation marker is replaced by the new recap

  Scenario: Recap preserves a leading inline code marker
    Given the recap starts with the inline code marker "`list_directory_sessions`"
    When the summary is cleaned before rendering
    Then the opening marker is not removed
    And the inline code marker remains balanced around "list_directory_sessions"

  Scenario: Recap marker aligns with the native working spinner
    Given the recap widget is displayed above the editor
    When the recap content is rendered
    Then the recap marker starts with one leading space like native working rows
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

  Scenario: A stored recap is reused only while it is the displayed one
    Given an exchange already has a completed recap request
    When the same exchange is recapped again while that recap is displayed
    Then the stored result is reused
    When a restored recap replaces it for the same exchange
    Then the stored result is not reused for the replaced recap

  Scenario: Recap generation times out safely
    Given recap generation does not complete before its timeout
    When the timeout is reached
    Then the request is cancelled
    And the previous recap is shown again

  Scenario: The recap budget bounds the whole request
    Given credential lookup for a recap request never returns
    Or a recap provider ignores cancellation and never resolves
    When the recap budget is reached
    Then the caller receives an empty recap instead of waiting forever
    And no provider completion is started without credentials

  Scenario: A widget refresh failure never fails a completed recap
    Given a recap was generated and persisted
    And refreshing the recap widget fails
    When the recap request settles
    Then the request still succeeds with the generated recap
    And the widget failure is reported as a warning rather than thrown

  Scenario: Pre-cancelled recap generation does not authenticate or complete
    Given recap generation receives an already aborted signal
    When the recap request starts
    Then it returns an empty recap
    And it does not request credentials or call the provider

  Scenario: Cancelling during authentication prevents provider completion
    Given recap authentication is still pending
    When the request signal is aborted before credentials resolve
    Then it returns an empty recap
    And it does not call the provider

  Scenario: A provider that ignores cancellation cannot publish a late recap
    Given the provider resolves after the request signal is aborted
    When the late response is received
    Then it returns an empty recap

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

  Scenario: Headless child sessions do not start recap generation
    Given a non-TUI child session is processing a consolidation prompt
    When the agent turn settles
    Then recap generation is not started
    And the child can exit without a stale-widget error

  Scenario: Headless recap commands do not start generation
    Given a non-TUI session
    When the user runs /recap now
    Then recap generation is not started
    And the user is told recap requires the TUI

  Scenario: Background recap ignores stale session context failures
    Given recap generation is running in a TUI session
    When the session is replaced before generation finishes
    Then the stale append failure is handled
    And no unhandled rejection is emitted
