Feature: Real model semantic contracts

  Scenario: Delivered domain guidance keeps glossary facts separate from implementation
    Given the domain-modeling procedure is delivered through the resolver bundle
    When an agent records vocabulary and unresolved domain questions
    Then it keeps implementation paths, function behavior, tests, and unresolved policy out of the glossary
    And it does not state a universal policy while the same decision remains unresolved

  Scenario: Delivered review guidance treats unresolved scope creep as a failed Spec verdict
    Given the code-review procedure is delivered through the resolver bundle
    When a candidate adds behavior that is not confirmed by the originating spec
    Then the review records that behavior as a Spec finding
    And a non-breaking fallback does not become PASS without an explicit compatibility requirement

  Scenario: Delivered questionnaire guidance separates observed behavior from decisions
    Given the to-questionnaire procedure is delivered through the resolver bundle
    When an agent writes context and decision questions from a code and spec gap
    Then current behavior is stated only when verified and target behavior remains distinct
    And each question asks for one independent decision

  Scenario: A prototype result does not settle an untested policy
    Given a throwaway numeric prototype answers a concrete representation question
    When its result exposes floating point error
    Then its report distinguishes measured results from proposed production choices
    And it leaves untested rounding policy unresolved

  Scenario: Interface designs distinguish requirements from proposed invariants
    Given the design sources leave some domain policies undecided
    When alternatives propose invariants and error modes
    Then the report separates sourced requirements from proposed invariants
    And it labels unsupported constraints as assumptions or unresolved decisions
