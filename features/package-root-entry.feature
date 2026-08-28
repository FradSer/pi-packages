Feature: Package-root index entry points
  Pi packages with runtime entry points expose a stable package-root index.ts,
  following the pi-mcp-adapter convention, while implementation modules remain
  internal composition details.

  Scenario: Every runtime package declares the package-root entry
    Given the repository contains runtime Pi packages
    When Pi resolves each package manifest
    Then its extension entry is exactly "./index.ts"
    And the root index.ts file exists
    And the root index.ts file is included in the published files

  Scenario: Multi-module packages compose registration through the root entry
    Given a runtime package contains multiple implementation modules
    When Pi loads its root index.ts
    Then the root entry registers each extension exactly once
    And registration does not depend on directory discovery order

  Scenario: Workflow harness packages use a package-root extension
    Given a package orchestrates internal workflow procedures
    When its package manifest is inspected
    Then its extension entry is exactly "./index.ts"
    And its procedures are not declared as recursively discoverable skills
