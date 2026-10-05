Feature: Subagent tools activate without rewriting an established prompt prefix

  Scenario: A compatible fresh session exposes only the loader
    Given the provider explicitly supports transcript-anchored tool additions
    When a fresh session starts
    Then subagents_enable is active and the intent tools are inactive
    And unrelated tools keep their selection

  Scenario: Authorized delegation can select the complete family without spawning
    Given a lazy subagent tool selection
    And delegation is separately authorized by the user or applicable instructions
    When subagents_enable is called
    Then the five intent tools are active for the next model request
    And no child starts during activation
    And activation changes availability only, never security authorization

  Scenario: An incompatible provider keeps a stable eager selection
    Given the provider cannot represent tool changes without a transcript checkpoint
    When the session starts
    Then the intent tools stay active and the loader is inactive

  Scenario: Switching models retains the session's selection
    Given subagent selection already established
    When the model changes mid-conversation
    Then activation does not alter the selected tools

  Scenario: An active branch restores its recorded selection
    Given the transcript records intent tool or loader additions and removals
    When the session starts or navigates its tree
    Then that active branch's selection is restored

  Scenario: Explicitly excluded tools are not activated
    Given the configured tools omit an intent tool or the loader
    When the session starts or activation is requested
    Then activation respects that configured exclusion

  Scenario: Loader results expose schema-matching activation facts
    Given the loader with an empty flat input schema
    When activation succeeds, a tool is unavailable or native selection fails
    Then outputSchema validates structuredContent with outcome and no-child-started facts
    And success identifies enabled tools
    And returned errors identify a refusal code and unavailable or missing tools
    And existing details remain available to UI and test callers

  Scenario: Short loader help distinguishes selection from permission
    Given a registered loader
    When its model-facing definition is read
    Then its short description and snippet promise selection without child creation
    And extended prompt guidelines preserve the separate delegation authorization requirement
    And no fake authorization parameter is added
    And annotations disclose non-read-only idempotent local selection without external effects

  Scenario: Activation failure diagnostics are bounded without mutating their source
    Given native selection throws a long diagnostic containing terminal controls
    When the loader returns the failure
    Then content, details and structuredContent share sanitized bounded error text
    And shortening uses the existing diagnostic truncation marker
    And the original thrown diagnostic remains unchanged

  Scenario: Branch removals and eager provider restoration preserve unrelated tools
    Given native selections on two branches with intent or loader additions or removals
    When the active tree branch changes or configured tools exclude an entrypoint
    Then only the current branch and available entrypoints determine the selection
    And unrelated selected tools remain unchanged
