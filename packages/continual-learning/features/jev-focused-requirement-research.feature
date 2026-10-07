Feature: Research focused requirement data without granting learning authority
  Scenario: A source-backed requirement is passed directly to the judgment
    Given a validated original user span and complete resulting Memory bodies
    When the focused research question is prepared
    Then the requested fragment and whole original user entry stay byte identical
    And numeric source coordinates are validated by code rather than sent as semantic data
    And the original positive and negative criteria remain unchanged

  Scenario: Invalid source or labels are supplied
    Given a fabricated quote, invalid source offset or evaluation-only label
    When the research question is prepared
    Then it is rejected before inference
    And neither research variant grants write or extraction authority

  Scenario: Real judgments do not establish a net quality gain
    Given unchanged Chinese and English development labels and fixed thresholds
    When both question variants are compared in the same bounded request
    Then missed requirements and false holds are reported separately
    And missing or failed responses remain unavailable rather than complete
    And development results alone do not authorize production adoption
