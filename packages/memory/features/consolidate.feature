Feature: Memory management with auto-memory guidance and manual consolidation
  The memory extension provides an auto-memory prompt guidance toggle and manual
  consolidation via the /memory menu and /consolidate command.
  When auto-memory is on, prompt guidance is injected telling the LLM to capture
  and organize durable decisions/preferences into memory on its own when needed.
  Consolidation is NEVER triggered automatically by context fill or agent settle;
  it only runs on manual user invocation in an async background child process.

  Background:
    Given the @fradser/pi-memory package is installed

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
    Then no automatic consolidation child is spawned

  Scenario: Dedicated /consolidate command is a sibling of /memory
    Given the user types /consolidate
    Then the extension spawns manual consolidation without opening the menu

  Scenario: Manual consolidation spawns a non-interactive child Pi process
    Given memory consolidation is manually started
    Then a child Pi process is spawned non-interactively (--print --mode json --no-session)
    And the consolidation procedure is passed to it
    And no follow-up message blocks the current session

  Scenario: Shows a dreaming widget above the input editor while consolidating
    Given a consolidation child was just spawned
    Then ctx.ui.setWidget renders a "dreaming" indicator above the editor
    And the widget is cleared when the child exits

  Scenario: Only one dreaming consolidation runs at a time
    Given a consolidation child is still running
    When another consolidation is triggered
    Then no second consolidation child is spawned
    And the user is notified that consolidation is already running

  Scenario: Reports success only after verified consolidation evidence
    Given a child exits with code 0
    And its JSONL has a successful tool execution, a passing full validator, and a G1 through G8 report
    Then the extension notifies that memory was consolidated

  Scenario: Diagnoses a zero-exit child with no verified consolidation
    Given a child exits with code 0
    And its JSONL has no completed tool work, passing full validator, or G1 through G8 report
    Then the extension does not claim that memory was consolidated
    And it reports which verification evidence is missing
