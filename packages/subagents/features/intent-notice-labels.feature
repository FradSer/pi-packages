Feature: An intent child's display name stays consistent through failures

  Scenario Outline: A child ends before delivering an answer
    Given an intent child whose display label differs from its session name
    When <failure> prevents delivery of its answer
    Then the ended notice uses the original display label
    And its exact session attribution remains unchanged
    And the row reports ended rather than completed work

    Examples:
      | failure                        |
      | an unexpected process exit     |
      | an unconfirmed child transport |
      | two failed result deliveries   |
