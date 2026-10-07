Feature: Simulate independent Memory subsets without write authority
  Scenario: Supported Memory is independent of a held candidate
    Given complete diagnostic reviews bound to the original evidence and candidates
    And all original pair judgments prove independence at unchanged thresholds
    When the research simulation runs
    Then only the fully supported candidate is counted as recoverable
    And every other original index remains held
    And no plan is applied or rewritten

  Scenario: Independence or complete review is missing
    Given a missing pair, uncertain relation, dependency, conflict or duplicate
    When the research simulation runs
    Then no affected candidate is counted as recoverable
    And missing or stale bindings hold the complete original set

  Scenario: Source, model or operation identity changes
    Given changed evidence, existing Memory, candidates or model
    Or a rewrite, deletion or Harness operation
    When the research simulation runs
    Then the complete original set remains held
    And no original text or filesystem write is emitted

  Scenario: Full evidence cannot pass the original review preflight
    Given sensitive or oversized original evidence or existing Memory
    Or omitted actual counterevidence windows or denied private Memory access
    When the research simulation runs its local production preflight
    Then the complete original set remains held
    And the preflight forwards no external request
