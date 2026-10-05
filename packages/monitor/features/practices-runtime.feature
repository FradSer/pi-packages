Feature: Robust runtime scheduling and startup
  Scenario: Wall clock changes during monitoring
    Given a running monitor with a monotonic elapsed clock
    When the wall clock moves backwards or forwards
    Then timeout, matched and stopped results retain a nonnegative elapsed duration

  Scenario: Matcher cannot be constructed
    Given a command requiring a matcher worker
    When synchronous worker creation fails
    Then the monitor terminates with an explicit failure and reclaims its process group

  Scenario: Brief output burst exceeds the matcher soft watermark
    Given a command writing many short lines followed by its result contract
    When matcher evaluation temporarily lags behind both output streams
    Then pipe reading pauses and resumes without skipping contract evaluations
    And the result resolves successfully within the deadline
