Feature: Isolated real-model identity and capability Memory study
  Scenario: Repeated temporary work stays temporary
    Given no disk definition and three identical task types
    When real Pi children run and accept next input
    Then no durable identity or Memory is created
    And each accepted input produces one attributed result
  Scenario: Saved identity persists data without persisting processes
    Given an explicitly authored fixture identity
    When work settles, next input runs, and the child stops and restarts
    Then handles bind exact incarnations and retired handles are refused
    And the private parent history and Memory remain
  Scenario: Read-only learning does not automatically become accepted Memory
    Given a saved read-only reviewer with agent_memory
    When it appends and proposes a reusable lesson
    Then append is refused and propose is an unaccepted candidate
  Scenario: Learned capabilities are measured on heldout reviews
    Given a model-authored capability from a training review
    When matched heldout reviews run with and without accepted Memory in new parent histories
    Then tool transcripts prove index injection and full entry reads
    And semantic findings, false positives and failures are reported separately
