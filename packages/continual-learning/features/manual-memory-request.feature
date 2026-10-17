Feature: Explicit memory requests through the simple command surface
  Scenario: Remember project knowledge with automatic learning disabled
    Given automatic learning and its three automatic phases are disabled
    When the user runs /memory Remember the project build convention
    Then a read-only selector and Memory planner receive the exact request
    And the parent validates and saves the Memory with a real receipt
    And shared Memory matches its canonical private copy byte for byte
    And Harness and AGENTS.md remain unchanged

  Scenario: Explicit preference remains private
    Given the user asks /memory Remember that I prefer concise updates
    When the planner proposes a private preference grounded in that request
    Then the parent saves it only in the private Memory root
    And no preference body or private index entry appears in shared Memory

  Scenario: The selector cannot broaden an explicit Memory request
    Given a selector requests Harness and AGENTS.md phases
    When it handles an explicit /memory request
    Then the parent limits the dossier and pipeline to Memory

  Scenario: Secrets are rejected before planning
    Given a memory request contains a credential
    When the user submits it with /memory
    Then no learning worker starts
    And the rejection does not repeat the credential

  Scenario: Current maintenance requests retain their real chronology
    Given an older task contains user restrictions and observed source results
    When the user later submits a Memory maintenance command
    Then unchanged older evidence precedes the exact current request
    And the dossier identifies the current request by its retained index
    And fresh source observations preserve that request index
    And omitted evidence remains marked incomplete

  Scenario: Large older context does not prevent a bounded explicit request
    Given the preceding task contains an oversized user message and many tool results
    When the user asks /memory to remember a short new fact
    Then the explicit request and recent verification remain unchanged
    And older whole entries are omitted within the evidence budget

  Scenario: An invalid proposal does not become a successful memory
    Given the Memory planner returns a proposal without request evidence
    When the parent validates the proposal
    Then no learned Memory is saved
    And the result reports rejection instead of success

  Scenario: Consolidation completion exposes only the supported common option
    When the user asks for /consolidate argument completions
    Then only full is offered
    And backfill remains an explicit compatibility diagnostic

  Scenario: Compact Memory discovery is reused while retained in the branch
    Given project and private roots may contain duplicate filenames
    When successive user turns use an unchanged Memory index
    Then one filename and description per deduplicated entry is retained without source suffixes or entry bodies
    And the unchanged reference is not appended after every user input
    And a changed index replaces the old reference and compaction or branching restores a missing current reference
    And reference metadata never enters system instruction authority

  Scenario: Actual on-demand reads participate in automatic correction
    Given the model successfully reads an indexed Memory file during a settled task
    When automatic learning selects the correction scope
    Then the parent pairs the exact prior read invocation and successful result
    And the read Memory is revisited even if the selector omitted it
    And failed reads, unmatched or duplicate call identities, user text and unrelated paths do not nominate Memory
    And nomination is neither independent factual evidence nor mutation authority
    And explicit Memory requests retain their requested scope

  Scenario: Explicit consolidation retains its current invocation separately
    Given an original task and a later /consolidate command
    When the parent captures each learning run
    Then the current raw command is bound to that run and project outside source entries
    And its digest covers the complete actual source entries
    And backfill retains the original task and its original citations unchanged
    And the current invocation session is distinct from the historical task session
    And the invocation proves only that the named maintenance procedure was requested
    And privacy, temporary-only, no-remember and preservation restrictions still apply
    And quoted commands, historical invocations and automatic replay grant no current authority
    And a changed binding stops review before a model request
