Feature: Reproducible real-process accuracy matrix
  Scenario: Explicit result contracts distinguish completion from progress
    Given real isolated shell commands produce synthetic stdout and stderr
    When a monitor observes anchored success and failure sentinels
    Then status, matched text, named payload, identity and notification count agree with the contract
    And a zero exit without a match is result_missing

  Scenario: Output boundaries and budgets remain explicit
    Given Unicode, CRLF, ANSI, split writes, bursts and bounded captures
    When each command is monitored with a predetermined contract
    Then complete physical lines are matched without silent fragment matches
    And clipped JSON is disclosed rather than parsed

  Scenario: Cancellation and repeated concurrency preserve ownership
    Given concurrent monitors and seeded repeated terminal races
    When a monitor times out, stops, shuts down or completes
    Then each waiter receives exactly one terminal result for its own unique ID
    And shutdown reclaims every owned process group

  Scenario: An unterminated idle prefix is a documented heuristic
    Given a writer pauses beyond the 150 millisecond idle window after DONE
    When it intends to append an invalidating suffix later
    Then an anchored DONE contract may already resolve successfully
    And this case is reported as a design limit rather than proof of exact completion
