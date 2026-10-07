Feature: Freeze the experimental composed policy in real-project images
  Scenario: Experimental image enables only known Memory options
    Given the host package uses the ordinary Jev constructor
    When a composed-policy image is prepared
    Then only the copied constructor enables independent and composed Memory application
    And the host source is unchanged
    And the original and modified source hashes are retained

  Scenario: Bind installed experimental bytes
    Given an explicit composed-policy image digest
    When the installed image source digest is calculated
    Then its actual source bytes match that digest
    And it differs from the ordinary image digest

  Scenario: Preserve ordinary default
    Given no experimental policy is requested
    When a project image is prepared
    Then its ordinary source bytes remain unchanged
