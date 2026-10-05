Feature: Temporary roles belong to the parent session

  Scenario: A confirmed parent shutdown drops temporary definitions
    Given a temporary child and its in-memory standing role
    When the parent shuts down and child closure is confirmed
    Then that child is marked stopped
    And its session-only role no longer resolves
    And that exact handle releases resident and hosted control closures
    And saved disk definitions and their data remain unchanged

  Scenario: Unconfirmed closure keeps execution facts honest
    Given a child whose closure cannot be confirmed during shutdown
    When shutdown handles the outcome
    Then its live incarnation is not falsely marked stopped
    And its shutdown intent remains recorded
    And its resident and hosted control bindings remain available for diagnosis

  Scenario: Shutdown cleanup cannot retire a successor
    Given a shutdown snapshot names one exact incarnation
    When confirmed closure is followed by a replacement under the same name
    Then cleanup releases the old handle only
    And the replacement keeps its input controls and current state

  Scenario: Already-stopped handles do not retain runtime closures
    Given a stopped incarnation still owns resident or hosted control bindings
    When its parent extension shuts down
    Then those stopped-handle closures are retired without terminating another process
