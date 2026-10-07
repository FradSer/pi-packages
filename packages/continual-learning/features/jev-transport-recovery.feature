Feature: Jev transport recovery without inventing a result

  The Jev memory review needs every evidence window to complete before it can
  decide. A connection-level transport failure in one window previously
  discarded the whole review. A bounded retry re-issues the same frozen request,
  so it cannot invent a decision, and the failure class stays recorded.

  Scenario: A connection failure recovers on the second attempt
    Given a Jev memory review whose first request fails at the connection level
    And the second request for the same frozen evidence succeeds
    When the judge evaluates the candidate
    Then the review decides on the recorded answer
    And the telemetry records one retried request
    And no failure kind is recorded

  Scenario: A connection failure that persists
    Given a Jev memory review whose requests keep failing at the connection level
    When the judge evaluates the candidate
    Then the review proposes without a decision
    And the telemetry reason is unavailable
    And the telemetry records the connection failure kind and one retry
    And no provider error text appears in the result

  Scenario: A status-bearing failure is not retried
    Given a Jev memory review whose request fails with HTTP 500
    When the judge evaluates the candidate
    Then the review proposes without a decision
    And the telemetry records the HTTP status and the http failure kind
    And no retry is recorded

  Scenario: A timeout is not retried
    Given a Jev memory review whose request times out
    When the judge evaluates the candidate
    Then the telemetry reason is timeout
    And no retry is recorded