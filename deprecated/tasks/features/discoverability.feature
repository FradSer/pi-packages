Feature: Passive task tool discovery
  Scenario: Tools describe their own use
    When Tasks loads
    Then all four tools have prompt snippets and descriptions
    And no capability note is injected into model requests
