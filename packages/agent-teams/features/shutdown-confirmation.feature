Feature: Confirm resident shutdown before releasing ownership
  Scenario: A registered child does not confirm termination
    Given a resident child holds a resource-scoped board task
    When shutdown is requested and child termination remains unconfirmed
    Then shutdown reports failure rather than success
    And the resident is not marked stopped
    And its board task and resource ownership remain held
    And no stopped summary is delivered

  Scenario: A stopping child eventually closes intentionally
    Given a previous shutdown could not confirm child termination
    When the child later emits close
    Then its close is handled as requested rather than unexpected
    And its confirmed stop time is recorded for its spawn incarnation

  Scenario: Stop evidence survives teammate name reuse
    Given a teammate incarnation has a confirmed stop time
    When another incarnation reuses its name
    Then the earlier stop time remains available until runtime reset

  Scenario: A stopping child cannot accept new work
    Given a previous shutdown could not confirm child termination
    When the leader attempts to deliver another assignment
    Then the assignment is rejected until shutdown is resolved

  Scenario: A repeated shutdown confirms close
    Given a previous shutdown could not confirm child termination
    When shutdown is retried and the child closes
    Then shutdown reports confirmed completion rather than a pending request

  Scenario: An absent child can be finalized
    Given a resident has no registered child
    When shutdown is requested
    Then its ownership is released and its confirmed stop time is recorded
