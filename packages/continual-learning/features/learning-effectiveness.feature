Feature: Paired model task effectiveness evaluation

  Scenario: A baseline provider failure cannot satisfy the baseline precondition
    Given the baseline arm exits with a provider error
    When the effectiveness report is validated
    Then the report is rejected before success rates are used

  Scenario: Exact answer scoring rejects uncertain or substring answers
    Given a held-out task declares the exact answer "canary"
    When the model answers "unknown; canary" or "canaryish"
    Then the task fails

  Scenario: Candidate knowledge comes from a native Memory body read
    Given the candidate Memory description does not contain the answer
    And the candidate task declares a required Memory body marker
    When the Pi JSON transcript contains a successful native read of that exact file
    Then the read start and end share a tool call id
    And the canonical path is under this run's project `.memory` root
    And the read result contains the marker

  Scenario: Provider configuration is frozen for the complete paired suite
    Given the source auth file changes after the first task arm starts
    When later arms are launched
    Then every arm uses the initial private auth snapshot
    And the changed source file is never overwritten
