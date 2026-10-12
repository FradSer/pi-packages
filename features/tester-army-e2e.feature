Feature: Deterministic official e2e CLI acceptance
  # Documentation/CI acceptance: not a test discovered by the runner's test glob.
  # Workflow uploads require a hosted run; local report checks cannot prove upload.
  @manual-ci
  Scenario: Default CI execution retains actionable reports without paid calls
    Given the official CLI configuration and no provider credentials
    When the deterministic suite runs in CI mode
    Then JSON, JUnit and Markdown reports are written
    And failed attempts retain their trace pages
    And the PR workflow runs the default suite and uploads its artifacts

  # tests/official-e2e/installation.e2e.ts: complete workspace settings pass the installation CLI
  @zero-paid
  Scenario: Valid isolated package settings pass the real CLI audit
    Given temporary settings listing the workspace Pi packages
    When the official e2e runner invokes the installation audit CLI
    Then the command exits successfully and reports the installed package count
    And no model or live user settings are used

  # tests/official-e2e/installation.e2e.ts: dead package sources fail with a located diagnostic
  @zero-paid
  Scenario: A dead source is reported as a failing audit
    Given temporary settings containing a nonexistent local package source
    When the official e2e runner invokes the installation audit CLI
    Then the command exits with code 1 and identifies the dead settings entry
    And no model or live user settings are used

  # tests/official-e2e/monitor-native.e2e.ts: real Pi delivers its monitored child result to the original session
  @zero-paid
  Scenario: A real Pi session receives the result of its monitored child command
    Given an isolated real Pi CLI with the existing offline monitor fixture
    When Pi calls monitor_start and the real child emits DONE_NATIVE
    Then the terminal result reports success for that monitor exactly once
    And the original session receives the matched result before its final answer
    And private progress stays out of the returned tool content in provider context
    And no remote model or semantic service is called

  # tests/official-e2e/monitor-native.e2e.ts: real Pi startup failures retain subprocess diagnostics
  @zero-paid
  Scenario: A real Pi startup failure retains subprocess diagnostics
    Given isolated offline Pi is asked to select a nonexistent provider
    When the real CLI exits unsuccessfully before a model request
    Then stdout and stderr are retained in a unique native evidence directory
    And stderr identifies the unavailable provider
    And the isolated settings are removed

  # tests/official-e2e/monitor-workflows.e2e.ts: table-driven real Pi acceptance.
  @zero-paid
  Scenario: Real Pi confirms finite verification outcomes through monitor
    Given an isolated real Pi session and the existing transport fixture
    When monitor runs the project typecheck or an intentionally invalid TypeScript file
    Then valid source succeeds with a parsed final JSON result
    And invalid source fails with its compiler diagnostic and nonzero exit code

  @zero-paid
  Scenario: Real Pi does not mistake intermediate output for completed verification
    Given a finite monitor contract using completion exit
    When a success candidate is followed by exit code 7 or the deadline
    Then the returned result reports failure or timeout instead of success
    When JSON is malformed or the command exits without its sentinel
    Then the returned result reports invalid_json_result or result_missing
    And each outcome returns once to the original session without a duplicate message

  @zero-paid @pytest
  Scenario: Deterministic monitor acceptance has no model entry point
    Given monitor outcomes are fully expressed by exact runtime assertions
    When the project's current E2E scripts and configuration are inspected
    Then no monitor AI execution or evidence classification entry remains active
    And no AI SDK dependency is required solely for monitor testing
    And BDD defines behavior and TDD drives implementation without a mandatory AI chain
    And earlier paid failures and costs remain historical evidence
