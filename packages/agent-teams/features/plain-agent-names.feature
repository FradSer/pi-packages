Feature: Plain Agent names
  Scenario: Delegate keeps the requested name
    Given an Agent named "reviewer"
    When the leader delegates Work to "reviewer"
    Then the resident name is exactly "reviewer" without a generated suffix
    And its exact session handle still includes its incarnation ID

  Scenario: Living names cannot be reused
    Given a living Agent named "reviewer"
    When the leader delegates again to "reviewer"
    Then the request is rejected as a duplicate living name
    And delegation to a distinct name creates independent Work

  Scenario: Start keeps the requested name
    Given an Agent named "context-markdown-fix"
    When the leader starts "context-markdown-fix"
    Then the resident name is exactly "context-markdown-fix" without a generated suffix
