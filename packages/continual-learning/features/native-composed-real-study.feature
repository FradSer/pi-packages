Feature: Bounded real Jev native composed comparison
  Scenario: Host credentials never follow a provider redirect
    Given a real HTTP redirect from a local test provider
    When the bounded proxy makes one upstream request
    Then the destination receives no request or authorization header
    And the original redirect is recorded as rejected

  Scenario: Standalone requests are narrowly authorized
    Given the frozen public native Memory fixture and an explicit composed study
    When a ready question uses all three exact original candidates and original user evidence
    Then it may use the study's bounded request budget
    And altered private content, unexpected state or uncontrolled labels are rejected before transport

  Scenario: Negative native results remain visible
    Given once-only bilingual original and composed arms with actual Jev and a fixed main planner
    When a valid fact is held or inference fails
    Then it remains a miss or missing coverage
    And it is not replaced by a favorable retry or declared full plugin improvement
