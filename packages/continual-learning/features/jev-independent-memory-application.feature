Feature: Parent applies only independently supported original new Memory
  Scenario: A mixed new Memory plan has an independently supported subset
    Given the parent validated the complete original plan, evidence and permissions
    And complete Jev candidate and pair reviews bind the same immutable original inputs
    When some original new Memory records pass every check and pair independence gate
    Then the full original plan is saved before any write
    And the parent validates the derived subset through its existing validator
    And the existing writer applies only original eligible records
    And the receipt counts applied records and retained pending records separately

  Scenario: Proof, identity, parent permission or preservation is missing
    Given stale, incomplete, uncertain or unavailable proof or forbidden original operations
    When the parent considers a subset
    Then no subset is applied
    And original explicit memory requests remain in the proposal or existing repair path

  Scenario: Evidence changes or application is cancelled
    Given a preserved original plan and a validated subset
    When source identity changes or current ownership is lost
    Then the unchanged parent writer refuses or rolls back application
    And the complete original proposal remains available
