Feature: Compare Memory repair generation without applying experimental output
  Scenario: Experimental text is not permission to change candidate intent
    Given an original frozen new-Memory plan
    When a generated repair is checked before semantic evaluation
    Then all identity fields, names, kinds and privacy classifications must match
    And the original production exact-quote normalizer must accept every citation
    And no operation or parent-derived write metadata may be introduced

  Scenario: A once-observed result is explicitly lasting
    Given a user explicitly asks to preserve a verified result and exact conditions
    When a durable-core clarification is supplied to the repair model
    Then it must preserve requested results and material compatibility exceptions
    And transient-only evidence cannot be converted into permanent knowledge
    And increased Jev allowance alone cannot justify adopting the clarification
