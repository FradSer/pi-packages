Feature: Worker capabilities stay bound to the started Assignment Attempt
  The current roster validates a started binding; it never silently replaces it.

  Scenario Outline: Roster drift cannot lend authority to an old turn
    Given a worker started an Assignment Attempt with a specific incarnation and Work Item
    When the roster changes its <identity>
    Then leader communication, peer communication, submission, release, and claims are rejected
    And no outbox, peer inbox, or submission intent is written for replacement Work

    Examples:
      | identity       |
      | assignment     |
      | Work Item      |
      | incarnation    |
      | living status  |
      | sender entry   |

  Scenario: Only a matching fresh assignment marker opens replacement Work
    Given a worker has closed its previous Assignment Attempt
    And the roster names a new Assignment Attempt
    When an ordinary prompt or a stale assignment marker is delivered
    Then the previous turn cannot communicate or submit as the new attempt
    When the matching assignment marker starts the new attempt
    Then work is disclosed and communication and submission use only that attempt

  Scenario Outline: Explicit outcomes close all worker side effects exactly once
    Given a worker started a direct or board Assignment Attempt
    When it submits <outcome> and the harness consumes the intent
    Then repeated submission, release, claims, leader messages, and peer messages are rejected
    And neither repeated same-attempt markers nor lifecycle resets reopen the attempt
    And settlement produces no duplicate automatic report

    Examples:
      | outcome |
      | success |
      | failed  |

  Scenario: Retained superseded Work keeps a cancellation acknowledgement path
    Given a worker retains closed superseded Work and its resource authority
    When cancellation guidance starts a turn for the same attempt
    Then work remains disclosed without authorizing success or a new claim
    And one failed submission or release can acknowledge cancellation
    And a prior successful candidate does not prevent this cancellation acknowledgement
    And repeated cancellation acknowledgements and communication remain rejected

  Scenario: Unassigned discussions and board notices remain usable
    Given the worker's matching live roster entry has no assignment
    When a fresh unassigned discussion starts
    Then leader and peer messages carry no Assignment Attempt
    And no automatic result is emitted and work stays hidden
    When a board notice starts a fresh unassigned turn
    Then work is disclosed and a claim intent can be queued without starting the Work
    And a completed prior attempt does not block this fresh unassigned turn

  Scenario: Recovery-held pending Work is not autonomous claim work
    Given pending Work has recoveryRequired set after failure
    When an unassigned worker lists or tries to claim that Work
    Then the board describes it as pending recovery rather than claimable
    And neither explicit-ID nor automatic claiming queues an intent for it

  Scenario: Lifecycle reset discards evidence without adopting new roster authority
    Given a worker started an attempt and has an unsettled answer
    When the session lifecycle resets while the roster names replacement Work
    Then settlement emits no old evidence and ordinary prompts cannot adopt the replacement
    And only its matching fresh assignment marker restores its Work capabilities
