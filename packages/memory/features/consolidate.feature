Feature: Memory management with auto-memory guidance and manual consolidation
  The memory extension provides an auto-memory prompt guidance toggle and manual
  consolidation via the /memory menu and /consolidate command.
  When auto-memory is on, prompt guidance is injected telling the LLM to capture
  and organize durable decisions/preferences into memory on its own when needed.
  Consolidation is NEVER triggered automatically by context fill or agent settle;
  it only runs on manual user invocation in the background.

  Background:
    Given the pi-memory-fradser package is installed

  Scenario: Injects auto-memory guidance when auto-memory is on
    Given auto-memory setting is on
    When before_agent_start runs
    Then it injects auto-memory prompt guidance telling the LLM to actively capture durable facts
    And it does not include auto-consolidation threshold instructions

  Scenario: Omits auto-memory guidance when auto-memory is off
    Given auto-memory setting is off
    When before_agent_start runs
    Then it does not inject auto-memory prompt guidance
    And it still injects existing active project memories if any exist

  Scenario: /memory management menu includes auto-memory toggle
    Given the user opens the /memory menu
    Then it offers options to consolidate memory, edit user instructions, edit project instructions, open memory folder, and toggle auto-memory
    And selecting toggle auto-memory flips the setting and persists it

  Scenario: No automatic consolidation runs on context fill or agent settle
    Given the agent settles after any turn regardless of context usage
    Then no automatic consolidation run is started

  Scenario: Dedicated /consolidate command is a sibling of /memory
    Given the user types /consolidate
    Then the extension starts manual consolidation without opening the menu

  Scenario: Select the memory consolidation model from the management menu
    Given the model registry contains available models
    When the user chooses model selection from the /memory menu
    Then the menu offers the available models
    And selecting one persists its provider and model for future consolidation runs

  Scenario: Manual consolidation scopes consolidation to the current session's related memories
    Given the current session contains durable memory candidates
    When manual consolidation starts
    Then it first extracts those candidates from the current session context
    And it reads the indexes and only related existing memory files
    And it does not scan unrelated memory files for consolidation
    And it clusters, checks staleness, merges, prunes, and privacy-checks that related set
    And it synchronizes safe results to .memory

  Scenario: Manual consolidation runs in the background without exposing an implementation requirement
    Given memory consolidation is manually started
    Then it runs without blocking the active session
    And the user sees progress and completion status
    And the user-facing behavior does not require a particular background agent implementation

  Scenario: Manual consolidation starts with the selected model
    Given a memory consolidation model is configured
    When memory consolidation is manually started
    Then the background consolidation run uses that provider and model
    And no follow-up message blocks the current session

  Scenario: Shows a dreaming widget above the input editor while consolidating
    Given a consolidation run was just started
    Then ctx.ui.setWidget renders a "dreaming" indicator above the editor
    And the widget is cleared when the run exits

  Scenario: Only one dreaming consolidation runs at a time
    Given a consolidation run is still running
    When another consolidation is triggered
    Then no second consolidation run is started
    And the user is notified that consolidation is already running

  Scenario: Reports success only after verified consolidation evidence
    Given a consolidation run exits with code 0
    And its JSONL has a successful tool execution, a passing full validator, and a G1 through G8 report
    Then the extension notifies that memory was consolidated

  Scenario: Diagnoses a zero-exit run with no verified consolidation
    Given a consolidation run exits with code 0
    And its JSONL has no completed tool work, passing full validator, or G1 through G8 report
    Then the extension does not claim that memory was consolidated
    And it reports which verification evidence is missing
