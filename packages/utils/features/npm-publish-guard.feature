Feature: npm publish and credential guard
  The utils package blocks bash tool calls that run package publishing or npm
  credential flows from the agent's non-interactive shell. These commands cannot
  complete there (2FA web-auth EOTP, masked 404 PUT on dead tokens), so the
  guard blocks the call and returns the corrected terminal procedure.

  Background:
    Given the pi-utils-fradser package is installed

  Scenario: Package publish commands are blocked across managers
    When bash runs "npm publish", "pnpm publish", "yarn publish", or "bun publish"
    Then the call is blocked with the publish label

  Scenario: Recursive and filtered workspace publishes are blocked
    When bash runs "pnpm -r publish", "pnpm --recursive publish",
      "pnpm --filter web publish", "pnpm --filter=web publish",
      "pnpm -F api publish", or "yarn workspace web publish"
    Then the call is blocked with the publish label

  Scenario: Dry-run allowance is scoped to its own invocation
    When bash runs "pnpm publish --dry-run"
    Then the call is allowed
    When bash runs "pnpm publish --dry-run && pnpm -F api publish"
    Then the call is blocked with the publish label

  Scenario: Credential and token flows are blocked without exemptions
    When bash runs "npm login", "npm adduser", "npm logout",
      "npm token create", or "npm token revoke --dry-run"
    Then the call is blocked

  Scenario: Env-prefixed invocations are blocked too
    When bash runs "NPM_CONFIG_REGISTRY=https://registry.npmjs.org npm publish"
    Then the call is blocked with the publish label

  Scenario: Command-position anchoring avoids false positives
    When bash runs "echo npm login", "cat pnpm-publish-notes.txt",
      or git commit with message "npm publish"
    Then the call is allowed
