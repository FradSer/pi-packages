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
