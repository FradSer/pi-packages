Feature: Confirm resident shutdown before releasing ownership
  Scenario: A registered child does not confirm termination
    Given a resident child holds a resource-scoped tasks task
    When shutdown is requested and child termination remains unconfirmed
    Then shutdown reports failure rather than success
    And the resident is not marked stopped
    And its tasks task and resource ownership remain held
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

  Scenario: Clean idle closure does not announce a crash
    Given a resident is idle with no unfinished work
    When its process exits with code zero and no signal
    Then its stopped state and confirmed stop time remain visible
    And its closure stays in the leader mailbox without a new leader turn
    And no unexpected-stop event or crash error is reported

  Scenario: Unread mail prevents passive clean closure
    Given an idle resident has unread mail addressed to its current incarnation
    When its process closes cleanly before inbox routing
    Then one unexpected-stop event reaches the leader
    And the close check does not consume or deliver the message
    And accepted task evidence stays unchanged

  Scenario: Malformed unread mail prevents passive closure
    Given an idle resident has unread inbox data with invalid syntax or message fields
    When its process closes cleanly before inbox routing
    Then one unexpected-stop event reaches the leader
    And the close check preserves the inbox and delivery evidence
    And accepted task evidence stays unchanged

  Scenario: Stale or already-delivered mail does not create a false alarm
    Given an idle resident owes no result or work
    And its inbox contains only earlier-incarnation or already-delivered messages
    When its process closes cleanly
    Then its closure stays passive
    And the close check changes no inbox offset or delivery record

  Scenario Outline: Interrupted work and process failure remain visible
    Given a resident has <work> work
    When its process exits with <code> and <signal> without a stop request
    Then one unexpected-stop event reaches the leader
    And unfinished work returns to pending under a recovery hold
    And an existing completed result stays completed

    Examples:
      | work       | code | signal  |
      | unfinished | 0    | none    |
      | completed  | 1    | none    |
      | completed  | none | SIGTERM |

  Scenario: An absent child can be finalized
    Given a resident has no registered child
    When shutdown is requested
    Then its ownership is released and its confirmed stop time is recorded
