Feature: Durable child history is partitioned by the parent Pi session

  Parent session identity is stable across --session recovery and differs
  between concurrent parent sessions. Memory and scratch remain shared by the
  durable identity; child conversation history follows the exact parent.

  Scenario: Two parent sessions overlap without sharing child history
    Given two real Pi parents use the same identity and project concurrently
    When each starts a durable child with a different history marker
    Then both parent session IDs are different and both children are live
    And their child session directories are different parent partitions
    And temporary children still use no durable session directory

  Scenario: Each recovered parent resumes only its own child marker
    Given parent A and parent B have each completed one durable child turn
    When each parent is restarted with its original --session file
    Then parent A keeps its original session ID and resumes only marker A
    And parent B keeps its original session ID and resumes only marker B
    And shared Memory and scratch data remain available to both identities
    And every native child closes cleanly

