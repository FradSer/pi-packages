Feature: Repository quality gates
  The repository exposes one local check command that exercises the package and
  root tests, TypeScript validation, and packed manifest validation.

  Scenario: The check command runs all local quality gates
    Given the repository dependencies are installed
    When a contributor runs `pnpm check`
    Then package and root pytest suites run
    And the extension TypeScript project is checked
    And every workspace package is pack-validated without publishing

  Scenario: Pull requests and releases share the quality gate
    Given GitHub Actions installs Node, pnpm, and pytest
    When a pull request or release workflow runs
    Then it runs `pnpm check` before release actions

  Scenario: CI installs the Bun runtime required by package tests
    Given package pytest fixtures invoke Bun subprocesses
    When a pull request or release workflow runs
    Then it installs Bun 1.4.1 before `pnpm check`

  Scenario: Local publishing uses the repository quality gate
    Given a contributor invokes the root `pnpm run publish` command
    When the command prepares the allowlisted release
    Then it runs `pnpm check` before the release script

  Scenario: Declared runtime sources are not hidden by ignore rules
    Given package manifests declare runtime files under ignored generic directories
    When the repository checks source visibility
    Then each declared runtime source is visible to version control
    And pack validation can include those sources in a fresh checkout

  Scenario: The daily quality gate includes official CLI acceptance without a model
    Given the workspace uses the official e2e runner and isolated offline Pi fixtures
    When a contributor runs pnpm check
    Then E2E types and the default real CLI acceptance suite run before packed-manifest validation
    And no paid evidence-classification test or provider credentials are used

  Scenario: Changeset validation reads real YAML frontmatter
    Given a pending Changeset with ordinary newline-delimited frontmatter
    When its package name matches a workspace manifest
    Then validation accepts it
    When it names an unknown or retired package
    Then validation fails with that package name
    And existing release metadata references current workspace package names
