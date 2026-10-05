Feature: Pi v1 development dependencies
  Scenario: The extension resolves the same Pi cohort it runs on
    Given the package targets Pi v1.0
    When code and runtime fixtures resolve Pi from the package directory
    Then coding-agent, pi-ai and pi-tui all resolve version 1.0.0
    And published core dependencies remain peers
    And executable live fixtures typecheck against that same cohort
