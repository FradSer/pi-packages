Feature: Finite workflows validate results at process exit
  Scenario: Complete records establish the success candidate
    Given completion is exit
    When a writer pauses inside READYISH or emits multiple success records
    Then only newline or EOF records match and the first success is retained

  Scenario: A success candidate does not hide a later failure
    Given a complete success record before the command finishes
    When the command fails, matches a failure record, times out, or is stopped
    Then the final result reports that failure instead of success

  Scenario: JSON must be valid for strict success
    Given a named json capture with completion exit
    When JSON is malformed or clipped
    Then completion fails with invalid_json_result
    And valid false, null and zero remain successful results

  Scenario: Repeated diagnostic compression preserves chronology
    Given alternating diagnostic records and adjacent repetitions
    When a failed monitor returns diagnostics
    Then only adjacent identical records collapse and record order is retained
