Feature: Historical worker reports do not become active leader instructions
  Worker-authored nonterminal reports are meaningful only while their originating
  assignment attempt remains current. Lifecycle metadata, never message prose,
  decides whether the leader should act on a report. Terminal accepted results
  and actionable harness diagnostics retain their delivery contract.

  Scenario Outline: Queued nonterminal reports become history when their attempt is retired
    Given a real Pi leader with a current assignment and an isolated deterministic provider
    And nonterminal worker reports have entered the native steering queue during a tool call
    When the originating attempt is <transition> before Pi requests its next response
    Then the original report evidence remains in session history
    And future provider context excludes the historical reports
    And unrelated user messages remain in provider context

    Examples:
      | transition               |
      | stopped                  |
      | released                 |
      | superseded               |
      | completed                |
      | replaced by a new spawn  |

  Scenario: Meaningful reports from an active attempt remain actionable
    Given a current open assignment in a real Pi leader session
    When an informational update and a decision request arrive during a tool call
    Then both reports reach the provider at the next safe delivery boundaries
    And their bodies and event identities remain unchanged in history

  Scenario: An accepted terminal result survives delayed arrival after shutdown
    Given a successful attempt-bound result has passed the harness acceptance pipeline
    When the process stops before Pi consumes the result
    Then the accepted terminal result remains in provider context
    And the original result and after-stop delivery metadata remain in history

  Scenario: A diagnostic from the harness survives worker shutdown
    Given a worker has stopped
    When the harness reports a lifecycle diagnostic requiring leader attention
    Then the diagnostic remains actionable regardless of worker lifecycle

  Scenario: A historical nonterminal report is retained without scheduling another response
    Given an originating attempt is no longer current at report handoff
    When the report reaches the leader delivery seam
    Then its evidence is appended as history rather than queued as active steering
    And no leader response is requested for that report
