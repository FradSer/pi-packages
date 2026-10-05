Feature: Live verification requires observed success in disposable state
  Scenario: Mixed learning retains durable personal preferences as private knowledge
    Given the same completed task states a personal response preference and a shared project fact
    And an existing project Memory needs correction
    When the automatic Memory planner interprets that task
    Then it retains the personal preference only in private Memory
    And it preserves the shared fact and corrects the existing Memory
    And it does not drop personal knowledge as scoped Harness guidance
    And the applied plan identifies the exact private entry as a preference
    And that plan and its post receipt bind to the same frozen snapshot
    And the automatic pipeline receipt contains only selector and Memory attempts

  Scenario: Failed observations cannot exit successfully
    Given a live probe reports a failed safety or persistence observation
    When its acceptance check completes
    Then it fails instead of merely printing a false flag

  Scenario: Direct runtime probes isolate agent state
    Given the caller has an ambient real agent directory
    When a live probe invokes Bun runtime code
    Then its agent directory is explicitly disposable
    And source agent files remain unchanged

  Scenario: Harness measurement requires ownership and correct decisions
    Given a learned rule blocks its positive case and allows its negative case
    But its parent-owned revision metadata is missing or invalid
    When the repeated learning measurement counts successes
    Then that trial does not count as learned and correct

  Scenario: Memory verification refuses unsafe file aliases
    Given a Memory root or Markdown entry is a symbolic link
    When a live probe reads the persisted Memory
    Then acceptance fails before reading the linked content

  Scenario: Native tool evidence binds content, paths and result order
    Given a native trace contains calls and returned tool results
    When acceptance proves that configuration or Memory bodies were read
    Then each result matches its preceding read call and exact target path
    And an index description cannot substitute for body-only evidence
    And a predecessor read result must arrive before the authoring write

  Scenario: Interrupted mutation recovery preserves external changes
    Given a failed mutation left a pending record and changed file bytes
    When recovery checks the record
    Then it refuses to overwrite unowned current bytes
    And an earlier applied change and unrelated files remain unchanged
    When the pending target is reconciled to its exact predecessor
    Then recovery abandons the pending record and a second check changes nothing
