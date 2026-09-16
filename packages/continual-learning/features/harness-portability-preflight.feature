Feature: Portable harness gates and mutation-free malformed-target rejection
  Scenario: Asset-only Pi installation retains native path gates
    Given PI_PACKAGE_DIR points to assets without private runtime modules
    When native write and edit paths are checked by the production tool-call hook
    Then harness aliases are gated identically to native write target resolution
    And unrelated writes and edits remain available

  Scenario Outline: Orchestration rejects malformed predecessors before receipts
    Given an existing harness file contains <predecessor>
    When applyHarnessConsolidationPlan applies a valid skill guidance plan
    Then the result is rejected
    And predecessor bytes and ownership metadata are unchanged
    And no pre receipt or post receipt is created
    Examples:
      | predecessor                  |
      | null                         |
      | an array or primitive root   |
      | malformed configuration containers |
