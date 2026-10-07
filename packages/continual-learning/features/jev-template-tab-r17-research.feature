Feature: Preserve independent Docker cohort evidence across a runner failure
  Scenario: Docker reports an owned container absent with different casing
    Given a completed workflow arm and its original immutable report
    When inspection explicitly reports the exact owned container absent
    Then casing alone does not invalidate the workflow outcome
    And daemon errors or another container name cannot establish absence

  Scenario: Continue only the unexecuted arms
    Given the first arm completed and the orchestration stopped after cleanup
    When remaining arms are authorized under a frozen continuation manifest
    Then the first arm and original runner failure remain preserved
    And the completed arm cannot be run again
    And remaining arms use the same frozen runtime and original acceptance gate
    And independent host processes stop before the next arm begins
