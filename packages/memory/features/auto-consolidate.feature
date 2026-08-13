Feature: Auto-consolidation at context fill threshold (async dreaming)
  When auto-memory is on, the memory extension watches the active model's
  context fill via ctx.getContextUsage and, once the session reaches a fraction
  of the context window (default 0.4 = 40%) after a user-typed turn while idle,
  spawns an ASYNC child Pi process to run the inline consolidate procedure —
  the current session keeps working. A "dreaming" widget above the input editor
  shows the background consolidation state until the child exits.

  Background:
    Given the @fradser/pi-memory package is installed
    And auto-memory is on
    And the default fraction consolidateAtContextFraction is 0.4

  Scenario: Reads context usage at agent settle
    Given the agent settles idle after a user-typed turn
    When the extension calls ctx.getContextUsage
    Then it reads percent, contextWindow, and tokens

  Scenario: Triggers an async consolidation at 40% context fill
    Given context percent reaches 42 and the context window is 1000000
    When the agent settles
    Then a child Pi process is spawned non-interactively (--print --no-session)
    And the consolidation procedure is passed to it
    And no follow-up message blocks the current session

  Scenario: Shows a dreaming widget above the input editor while consolidating
    Given a consolidation child was just spawned
    Then ctx.ui.setWidget renders a "dreaming" indicator above the editor
    And the widget is cleared when the child exits

  Scenario: Does not trigger below the 40% boundary
    Given context percent is 39
    When the agent settles
    Then no consolidation child is spawned

  Scenario: Tier-based firing prevents the consolidation run from re-triggering
    Given a consolidation was just triggered at 42% (tier 1)
    When the consolidation run settles at 45%
    Then no second consolidation is spawned

  Scenario: Only one dreaming consolidation runs at a time
    Given a consolidation child is still running
    When context percent reaches 80 (tier 2)
    Then no second consolidation child is spawned

  Scenario: Dedicated /consolidate command is a sibling of /memory
    Given the user types /consolidate
    Then the extension spawns the same consolidation as /memory's first item
    And the /memory management menu is unchanged

  Scenario: Child receives the session file for Step 0 capture
    Given a consolidation child is spawned
    Then the task includes the current session file path
    And the project cwd and harness memory dir

  Scenario: Disabled when auto-memory is off
    Given auto-memory is off
    Then no auto-consolidation fires regardless of context fill

  Scenario: Fraction of zero disables auto-consolidation
    Given settings.json sets consolidateAtContextFraction to 0
    Then no auto-consolidation fires

  Scenario: Auto-consolidation runs only in interactive TUI sessions
    Given the session mode is not TUI
    Then no auto-consolidation fires even at high context fill
