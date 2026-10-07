Feature: Observe independent learning effects without weakening acceptance
  Scenario: Memory is held but Harness can be exercised safely
    Given an isolated workflow whose Memory acceptance fails
    And a Harness probe that uses a local marker instead of a remote write
    When learning effects are observed
    Then recall is recorded as missing its Memory prerequisite
    And the native Harness probe still runs
    And the complete workflow remains failed

  Scenario: Recall fails after accepted Memory
    Given accepted Memory and a fresh session that fails recall
    When learning effects are observed
    Then the native Harness probe still runs
    And recall failure is preserved in final acceptance

  Scenario: Independent effects are all accepted
    Given Memory, fresh recall and native Harness probes that all pass
    When learning effects are observed
    Then each phase is recorded separately as passed
    And no phase receives write authority from the observer

  Scenario: Execution is cancelled
    Given a cancelled effect callback
    When learning effects are observed
    Then cancellation propagates without starting another model call
