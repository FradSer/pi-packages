Feature: pi-artifact wraps Open Artifacts behind an /artifact menu
  The package exposes the vendored Open Artifacts publishing CLI through one
  native Pi command menu following the /memory and git-agent patterns, keeps
  coda0.com as the recommended default instance, and stays instance-neutral
  beyond that recommendation — hosted-instance login is not a menu item.

  Scenario: The manifest registers one extension backed by shared pi-kit helpers
    Given the repository contains the pi-artifact package
    When Pi resolves its manifest
    Then the manifest carries the pi-package keyword
    And it registers exactly one extension at ./index.ts
    And the package declares @fradser/pi-kit as its only dependency
    And the published files include extensions, procedures, references, examples, vendor, scripts, and the README

  Scenario: The /artifact menu offers the four state workflows without login
    Given the /artifact command menu is inspected
    When its items are enumerated
    Then publish, update, status, and show are present
    And no item performs login or logout for a hosted instance
    And update and show pick a target artifact from the merged project manifest

  Scenario: Menu selections deliver full procedures into the session
    Given a menu item maps to procedures/<name>.md in the shipped package
    When the user selects it
    Then the full procedure is sent as a follow-up user message
    And every {{PKG_DIR}} placeholder is substituted with the package directory
    And the procedure references the bundled CLI under scripts/artifact.mjs

  Scenario: Natural-language requests route without a skill surface
    Given the package ships no skills and no skill manifest entry
    When a session asks to publish or update an artifact page
    Then the before_agent_start guidance block routes the request to the bundled CLI
    And the guidance names coda0.com as the recommended default instance

  Scenario: The bundled CLI defaults to coda0.com but stays instance-neutral
    Given no --api flag, OPEN_ARTIFACTS_URL, project config, or global config
    When loadConfig resolves the instance URL
    Then it falls back to https://coda0.com
    And explicit flags, environment variables, and both config files still win

  Scenario: Upstream provenance is documented and syncable
    Given the vendored trees come from coda0HQ/open-artifacts
    When UPSTREAM.md is inspected
    Then it records the source commit and the exact local changes
    And the local changes cover only the default-instance wiring
