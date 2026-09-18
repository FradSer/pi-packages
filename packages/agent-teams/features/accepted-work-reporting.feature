Feature: Accepted Work results reach the Leader without polling
  Submission, execution settlement, and result delivery have distinct identities.

  Scenario Outline: Explicit submission settles without a false finalization reminder
    Given an Agent owns Work and has sent an informational event
    And it queues one explicit success submission with result evidence
    When <ordering>
    Then the Work completes with that evidence
    And exactly one accepted result reaches the Leader with Work, attempt, and session identity
    And the Agent receives no finalization reminder
    And repeated settlement or intent draining does not duplicate the accepted result

    Examples:
      | ordering                                            |
      | the runtime drains the submission before settlement |
      | execution settles before the submission is drained  |

  Scenario Outline: Failure reports settle before releasing Work
    Given an Agent owns Work with execution still active
    When it submits a failed result through <channel>
    Then Work remains owned until execution settles
    When execution settles
    Then Work returns to pending with the failure evidence
    And exactly one failure report reaches the Leader with the original attempt identity
    And no finalization reminder is produced

    Examples:
      | channel              |
      | explicit submission  |
      | automatic finalizer  |

  Scenario Outline: Superseded holdings use the same submission rules
    Given an Agent owns superseded Work through <acquisition>
    When it reports success through <channel>
    Then the obsolete result is rejected without announcing completion
    And the original Work resources remain held
    When it acknowledges cancellation with a failed result through <channel>
    Then the original Work resources remain held until execution settles
    When execution settles
    Then only the obsolete holding is released and its Work stays superseded
    And the replacement Work stays pending

    Examples:
      | acquisition | channel   |
      | delegation  | automatic |
      | claim       | automatic |
      | delegation  | explicit  |
      | claim       | explicit  |

  Scenario: Fresh assignment publishes its binding before delivery
    Given the Leader assigns pending Work to an idle resident
    When its new Pi session accepts the assignment prompt before the next runtime tick
    Then the worker can read its current attempt and Work binding from the roster
    And its ordinary final answer is accepted without a finalization reminder

  Scenario: Duplicate failure cannot leave authority on a later attempt
    Given one failed submission is pending execution settlement
    And a duplicate failure for the same attempt is queued
    When execution settles and Work is released
    And the Work is assigned to the same resident again
    Then the later attempt can submit and complete normally
    And each attempt produces at most one terminal report

  Scenario: Informational mail preserves verification parking
    Given a Work holding is parked after repeated failed or inconclusive reviews
    When the Leader sends an ordinary agent_event
    Then the holding stays frozen with its resources retained
    And no worker execution or new verification starts
    And only explicit Work release and reassignment can authorize another attempt
    And feedback names that recovery path rather than ordinary steering

  Scenario: Historical terminal records carry no current completion authority
    Given a terminal outbox record has no current owned Work
    When the runtime drains that record
    Then it is retained as historical evidence only
    And no completed or failed Work result is pushed to the Leader
    And no Assignment Attempt is created or changed
    And ordinary messages cannot return that unaccepted evidence as a recorded result

  Scenario: Delayed submissions cannot complete a replacement attempt
    Given Work was released and assigned again to the same resident
    When a submission from the earlier attempt is drained
    Then the new attempt retains its Work without completing or releasing it
    And no accepted result is announced for the stale submission

  Scenario: Fresh-session reset failure releases explicitly assigned Work
    Given the Leader explicitly assigns pending Work to an idle exact session
    And same-attempt guidance is queued during the fresh-session reset
    When the reset fails, is cancelled, times out, or the process closes
    Then the Work is released with the reset failure reason
    And neither the assignment nor queued guidance reaches the old session

  Scenario: Reassigned Work cannot announce acceptance before settlement
    Given a resident completed a prior assignment
    And the Leader explicitly assigns a later Work attempt
    When its automatic final answer is drained before execution settles
    Then no completed report is delivered yet
    When execution settles
    Then the later attempt delivers its own accepted result exactly once

  Scenario: A verification gate delays the accepted result
    Given an Agent owns gated Work and returns an automatic final answer
    When execution settles and verification is still running
    Then the Leader receives no completed result yet
    And the Agent receives no finalization reminder
    When verification passes
    Then exactly one accepted result reaches the Leader

  Scenario: Communication cannot assign or retry Work
    Given a resident is unassigned or its previous Work is pending after failure
    When the Leader sends an ordinary agent_event
    Then no Work or Assignment Attempt is created or reclaimed
    And the receipt directs the Leader to explicit Work assignment

  Scenario: An unassigned Agent owes no terminal report
    Given an Agent has no current Assignment Attempt
    And it sends an informational event to the Leader
    When its execution settles
    Then no finalization reminder or unfinalized-report attention event is produced

  Scenario: A message after completion cannot create or reclaim Work
    Given an Agent completed a Work Item and remains resident
    When the Leader sends an informational agent_event to its exact session
    Then the event is handled without a duplicate Work ID error
    And no Work Item is created, reopened, or claimed
    And no new Assignment Attempt or execution starts for the closed work
    And the receipt exposes the recorded result without asking the Agent to resend it

  Scenario: Completed evidence is readable from the Work list
    Given a Work Item has completed with a result
    When the Leader calls work list
    Then the model-visible content includes bounded result evidence and its Work ID
    And the complete result remains in structured details

  Scenario: Ordinary answers complete owned Work regardless of acquisition path
    Given an Agent owns Work through an autonomous claim
    When it returns an ordinary final answer and execution settles
    Then the current attempt queues one submission through the Work acceptance pipeline
    And an explicit submission suppresses a duplicate automatic submission
    And an unassigned answer never fabricates Work

  Scenario: Accepted results interrupt the Leader only at safe boundaries
    Given a worker owns Work and its execution has settled
    And the Leader is in a tool call
    When the worker's result is accepted
    Then Pi queues the accepted report for the next safe tool boundary
    And delivery does not wait for the Leader's execution to settle
    And informational events retain their authored timestamp

  Scenario: Native Pi settles immediately after an explicit submission
    Given a native Pi worker owns a current Work Item
    When its model calls work submit with result evidence
    Then the tool ends the execution turn without another model request
    And exactly one attempt-bound submission remains for acceptance
    And the automatic finalizer emits no duplicate report

  Scenario: Long Work evidence has a bounded model-visible preview
    Given a completed Work Item has a long result
    When the Leader calls work list
    Then its model-visible result preview is bounded and identifies truncation
    And the structured Work details retain the complete result

  Scenario: Tool guidance keeps deliberate inspection separate from waiting
    When the Leader discovers the agent tool before delegating
    Then its guidance explains that results arrive automatically
    And it directs the Leader to end the turn when no independent work remains
    And sleep and repeated inspection are not a waiting protocol
