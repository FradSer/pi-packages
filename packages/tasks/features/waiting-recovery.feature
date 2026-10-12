Feature: Waiting task recovery display
  Scenario: Waiting details use native expansion
    Given one unfinished task and no new successful tool result
    When Pi settles with a transcript
    Then the waiting row shows only its headline and native expansion hint
    And Ctrl-O or a headline click reveals the complete recovery details
    And continuation rows keep their full details visible

  Scenario: Recovery details show the latest saved state
    Given a blocked task with a handoff and a previous recovery note
    When the waiting row expands
    Then the current blocker appears before the latest delta, verification, and outstanding work
    And the description is labeled Original plan
    And the recovery note is labeled Previous recovery

  Scenario: Handoff updates refresh waiting without another continuation
    Given an unchanged waiting snapshot
    When visible handoff fields change without a new successful tool result
    Then Pi records a new waiting snapshot
    And the automatic continuation allowance does not change
    And an identical snapshot is not recorded again

  Scenario: The same waiting component survives terminal resizing
    Given a waiting row in the real Pi CLI at 120 columns and 40 lines
    When the user expands it and resizes to 48 columns with 24 and 12 lines
    Then native expansion and collapse still work
    And the headline and recovery details remain available
    And Pi retains keyboard input ownership
