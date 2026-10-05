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
