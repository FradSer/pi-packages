Feature: Memory final verification belongs to the write transaction
  Scenario: Final receipt verification rejects already written new Memory
    Given the original plan and subset passed pre-application verification
    When final receipt verification fails after both Memory roots contain new records
    Then all Memory files and indexes return to their original state
    And newly created empty Memory roots are removed
    And history does not report an applied mutation
    And the original proposal remains available and the pipeline reports failure

  Scenario: Ownership is lost while final verification is pending
    Given the writer completed its provisional changes
    When cancellation occurs during asynchronous final verification
    Then the writer rolls back instead of committing its changes
