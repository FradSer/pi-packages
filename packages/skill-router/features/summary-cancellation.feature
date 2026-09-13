Feature: Cancelling collection summaries
  Scenario: Cancellation before summary generation
    Given the summary operation is already cancelled
    When workflow navigation summaries are requested
    Then no authentication or model request starts
    And cancellation is returned instead of fallback summaries

  Scenario: Cancellation during authentication or generation
    Given collection summaries are being generated
    When the operation is cancelled during authentication or the model request
    Then cancellation is propagated to the loading overlay
    And no later model request or installation starts
    And a late successful response cannot replace cancellation

  Scenario: The provider aborts summary generation
    Given the model request reports an abort
    When workflow navigation summaries are requested
    Then the abort is propagated instead of returning fallback summaries
