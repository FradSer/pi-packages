Feature: Verification gate reviewer isolation
  A completion gate is judged by a one-shot Pi child that carries no leader runtime.

  Scenario: The reviewer starts as a bare Pi process
    Given a Work Item submission enters its verification gate
    When the runtime builds the reviewer child options
    Then extension, skill, prompt-template, context-file, and theme discovery are all disabled
    And the child is ephemeral so no session record is persisted
    And the review cannot activate automatic memory learning or write memory files

  Scenario: The reviewer is granted read-only inspection tools
    Given a Work Item submission enters its verification gate
    When the runtime builds the reviewer child options
    Then the tool grant is read, bash, grep, find, and ls
    And no edit or write tool is granted
