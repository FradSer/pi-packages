Feature: Leader priority and assignment-scoped resident lifecycle
  Scenario: Leader direction overtakes pending peer traffic
    Given a resident is executing an assignment with pending peer mail
    When the leader supplies new direction
    Then native steering delivers direction before native peer follow-up

  Scenario: A stale working label cannot strand leader direction
    Given a resident sequence has settled but its roster still says working
    When the leader sends direction
    Then a native prompt starts a new run instead of queue-only steering

  Scenario: A terminal report does not fabricate execution settlement
    Given a resident reports completion while its tool batch is still running
    When the harness closes its direct assignment
    Then execution stays running until agent_settled

  Scenario: A late terminal report cannot close a newer assignment
    Given a resident has moved from assignment old to assignment new
    When a delayed terminal report names assignment old
    Then assignment new remains open

  Scenario: Reclaiming the same board task creates a new holding identity
    Given a worker releases a board task and reclaims it in the same spawn
    When a delayed terminal report names the previous holding
    Then the new holding remains reportable with a distinct assignment identity
    And the board task id remains unchanged

  Scenario: A new assignment needs its own terminal report
    Given an older assignment has a terminal report
    When a new assignment has no terminal report
    Then the current assignment is unfinalized

  Scenario: Peer events cannot carry terminal report status
    Given a worker addresses a peer
    When it supplies completed or failed status to agent_event
    Then the tool rejects the invalid terminal transition

  Scenario: Reports after terminal are explicitly rejected
    Given a worker has emitted its terminal report
    When another leader report is attempted before a new assignment prompt
    Then the tool returns a rejection rather than falsely claiming delivery
