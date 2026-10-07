Feature: Lossless evidence structure research
  Scenario: Nested session messages gain a direct structural view
    Given frozen support and review evidence with ordered session entries
    When a research request adds a structural view
    Then every original field and question is preserved
    And every derived field points to its exact original location
    And the view does not infer execution success or grant write authority

  Scenario: Unknown or ambiguous tool provenance remains unknown
    Given missing or repeated tool-call identifiers
    When references are derived from earlier assistant tool calls
    Then ambiguous references remain explicitly unresolved
    And a false isError value does not become an exit code

  Scenario: Invalid or oversized evidence fails before transport
    Given malformed evidence or a request exceeding the research byte bound
    When a structural request is prepared
    Then the preparation fails without an external request or file write
