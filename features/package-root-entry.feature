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

  Scenario: A skill collection router declares the package-root entry
    Given the repository contains the skill collection router runtime package
    When Pi resolves its package manifest
    Then its extension entry is exactly "./index.ts"
    And its manifest exposes no packaged skills
    And the root index.ts file exists
    And the root index.ts file is included in the published files

  Scenario: Package directories use concise names independently of npm package names
    Given the continual-learning and kit packages have published npm names
    When the workspace resolves package directories and dependencies
    Then their directories are named continual-learning and kit
    And workspace dependency links target the kit directory

  Scenario: Commit scopes describe the current package layout
    Given git-agent uses the repository scope configuration
    When package ownership descriptions are resolved
    Then every configured package directory names a current workspace package
    And every package directory has a dedicated scope
    And scope names are concise, unique identifiers
    And no scope description points to a removed package directory
