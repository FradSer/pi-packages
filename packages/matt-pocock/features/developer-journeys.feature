Feature: Developer tasks using real Pi v1 model calls
  Scenario: An agreed feature moves from requirements to local handoff
    Given the receipt discount decisions are recorded and the independent acceptance tests are RED
    When a developer uses idea-to-ship to implement the whole-receipt discount
    Then the model observes RED before GREEN, preserves existing API behavior, reviews the candidate and writes a handoff
    And the workflow reaches completed without a remote action

  Scenario: An incident fix preserves async cache concurrency
    Given a rejected cache entry prevents subsequent retries
    When a developer uses hard-bug to diagnose and fix it
    Then independent tests verify rejection retry, shared in-flight loads, independent keys and synchronous throws
    And the incident note, review and completed workflow correspond to the verified candidate

  Scenario: A cleanup retains strict configuration behavior across multiple turns
    Given a parser with nested conditionals already passes its public acceptance tests
    When a developer uses design, deslop, review and handoff in successive real model turns
    Then the same strict flags, port grammar, defaults and errors remain GREEN
    And all four procedure bundles and requested artifacts are observed
    And no fabricated RED or remote work is required

  Scenario: A terminal label alone cannot prove the requested journey
    Given a model completes a workflow without entering the requested implementation and review stages
    When the real-run validator checks the branch evidence
    Then the journey fails despite GREEN source behavior and completed status
    And restarting another work item cannot masquerade as the original journey

  Scenario: Cache retry does not evict another key
    Given one key is already cached and another key is in flight
    When a different key rejects and is retried
    Then the cached value and in-flight promise remain shared with unchanged loader counts
    And clearing all entries is rejected by the immutable acceptance tests
