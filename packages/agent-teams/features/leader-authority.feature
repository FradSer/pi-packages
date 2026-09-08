Feature: Leader authority and assignment-scoped completion guidance
  Scenario: First delegation includes the coordination contract
    Given no team exists when the leader starts a turn
    When the leader receives the spawning guidance
    Then it includes leader priority at the next safe boundary
    And it distinguishes yielding the turn from completing the user's task
    And it requires a terminal report for each current assignment before claiming completion

  Scenario: Leader direction takes precedence over worker plans and peer requests
    Given a worker is executing an assignment
    When the leader changes its scope or priorities
    Then the worker applies that direction at the next safe boundary
    And it does not wait until its original assignment completes
    And system instructions and user constraints remain authoritative

  Scenario: Reporting after terminal status requires a new assignment
    Given a worker has sent the terminal report for its assignment
    When it receives no new assignment
    Then it stops reporting instead of assuming supplemental reports will be delivered
