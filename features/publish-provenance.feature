Feature: Release publishing without local provenance assumptions
  The repository release script publishes its explicit package allowlist in
  dependency order and must remain runnable both in GitHub Actions and locally.

  Scenario: Local publishing does not force CI-only provenance
    Given the release script runs outside GitHub Actions
    When it publishes an unpublished package
    Then it does not pass --provenance to pnpm publish
    And npm authentication errors remain visible to the caller

  Scenario: CI publishing enables npm provenance
    Given the release script runs in GitHub Actions
    When it publishes an unpublished package
    Then it passes --provenance to pnpm publish

  Scenario: The release workflow publishes versions after version commits
    Given Changesets has already committed package versions and removed its changesets
    When the release workflow finds no changesets to publish
    Then it runs the explicit package release script
    And the release script publishes versions missing from npm
