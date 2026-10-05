Feature: Native recovery for a known premature provider stream closure
  The package classifies the known diagnostic. Pi owns retries, budgets, backoff and cancellation.

  Scenario: A temporary child loses the terminal provider event
    Given the provider reports stream disconnected before completion and stream closed before response.completed
    And the assistant message contains no tool call
    And native retry permits another attempt
    When message_end reaches the explicitly loaded recovery extension
    Then Pi retries that assistant response in the same sequence
    And the original input is not dispatched again
    And only the final settled result is delivered

  Scenario Outline: Native retry policy remains authoritative
    Given the exact premature-close failure and retry policy <policy>
    When the native sequence finishes
    Then attempt count follows that policy
    And unresolved failure remains an honest unanswered outcome

    Examples:
      | policy                    |
      | disabled                  |
      | exhausted after one retry |

  Scenario: Other failures retain their original classification
    Given an abort, authentication failure, quota failure, unrelated error or unfinished tool call
    When message_end reaches the recovery extension
    Then it does not replace that message
    And no package retry or replacement child starts
