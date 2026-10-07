Feature: Research exhaustive coverage of selected original user requests
  Scenario: Chinese and English requirements have exact source coverage
    Given selected original user entries contain conditions, negation, versions and multiple sentences
    When code partitions their original text without semantic extraction
    Then every original UTF-16 code unit belongs to exactly one source span
    And every span can be judged with the entire original entry as context
    And source coverage does not establish durable relevance or permission to write

  Scenario: Request coverage exceeds the bounded question capacity
    Given complete coverage needs more than 31 spans
    When the coverage is prepared
    Then the result is unavailable with a capacity reason
    And no partial list can be mistaken for complete coverage

  Scenario: The selected source is invalid or not a user entry
    Given invalid, duplicate or non-user selected entry indices
    When coverage is prepared
    Then the result is unavailable before inference
    And it does not grant extraction or write authority
