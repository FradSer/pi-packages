Feature: Deduplicate equal capture values without losing terminal information
  Scenario: Repeated captures use explicit references
    Given a terminal matcher returns many named captures with identical string values
    When monitor emits its model-facing terminal content
    Then the first capture value is emitted in full
    And later identical captures explicitly reference the first field
    And every capture can be reconstructed from its value or reference
    And structured terminal data and human expanded details retain all fields

  Scenario: Ordinary captures equal the complete parsed JSON
    Given a terminal result contains valid JSON and ordinary captures equal its complete serialization
    When monitor emits terminal content
    Then it emits the full JSON once and references it from the equal captures
    And JSON false, null and zero are retained

  Scenario: Unequal or untrusted values are preserved safely
    Given capture values contain Unicode, escaping or terminal control characters
    When monitor emits terminal content
    Then only exactly equal original strings share a reference
    And distinct values are not deduplicated by substring or sanitized appearance
    And diagnostic tails, parse errors and truncation disclosures remain visible
