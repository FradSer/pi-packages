Feature: Reserved npm placeholder packages
  The repository can publish minimal package shells to reserve names for
  future Pi functionality without claiming to implement them yet.

  Scenario: Placeholder packages expose only their public package shell
    Given the repository includes the pi-design placeholder package
    When its manifest and published file list are inspected
    Then pi-design uses version 0.0.1
    And pi-design exposes an empty ESM entry point
    And pi-design declares no Pi extensions or skills
    And the release allowlist includes pi-design

  Scenario: Real packages are not placeholders
    Given a package ships runtime skills or extensions
    When its manifest and entry points are inspected
    Then it does not use the empty placeholder shell
