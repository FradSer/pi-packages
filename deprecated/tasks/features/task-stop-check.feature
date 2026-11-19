Feature: Removed automatic task execution
  Scenario: Retired execution APIs are absent
    When a consumer imports the Tasks package
    Then automatic settlement and capability injection exports are absent
    And the status message renderer is absent
    And the four task tools remain available
