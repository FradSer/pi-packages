Feature: Frozen evidence in the existing Memory structural repair slot
  Scenario: Correct syntax without inventing durable scope
    Given an incremental Memory proposal with a structural error and frozen source evidence
    When Jev is enabled and the first repair is needed
    Then the same single read-only repair receives the hash-checked original evidence and selected Memory
    And temporary instructions do not become standing preferences
    And final parent validation and Jev judgment remain required
  Scenario: Frozen evidence is changed or repair is cancelled
    Given a bound snapshot and dossier
    When either digest differs or cancellation occurs
    Then no repair model request is started with invalid evidence
    And changes during repair prevent accepting its output
  Scenario: Repair preserves private classification
    Given a recognizable private proposal
    When repair changes its classification to safe
    Then repair is rejected without write authority
