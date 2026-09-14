Feature: Spend learning tokens only when durable value is plausible
  Automatic learning uses deterministic screening before any model call, shares one
  bounded exploration dossier, and accounts for every worker attempt.

  Scenario: Parent screening can skip an automatic run without tokens
    Given a frozen task contains no durable user statement, correction, or harness event
    When automatic learning evaluates the task
    Then no explorer or planner is launched
    And the receipt records zero calls and zero tokens

  Scenario: Automatic learning is lightweight
    Given automatic learning finds durable evidence
    When it selects phases
    Then it limits the run to evidence-backed phases and tighter automatic budgets
    But an explicit consolidation keeps the full manual behavior

  Scenario: Later planners share one exploration dossier
    Given Harness and AGENTS.md both have evidence candidates
    When their planning begins after verified Memory learning
    Then one read-only explorer produces a bounded immutable dossier
    And both planners receive the same dossier digest instead of independently exploring the full context
    And Harness and AGENTS.md planning may overlap
    But their validated mutations are applied sequentially

  Scenario: Retry policy preserves value
    Given a planner attempt fails
    When the parent classifies the failure
    Then automatic learning retries only a syntactically unusable Memory plan before mutation
    And automatic Harness and AGENTS.md planners do not retry
    And manual learning retries one pre-mutation plan-format or validation failure
    And provider, timeout, cancellation, output-limit, stale-input, and post-mutation failures never retry

  Scenario: Learning reports value and cost
    Given explorer and planner workers finish with usage metadata
    When the pipeline settles
    Then a receipt records each attempt outcome, duration, operations, retries, tokens, cache usage, and cost
    And the user receives a compact totals summary
