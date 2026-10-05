Feature: Pi v1 real-model observer isolation
  Scenario: The observer records only bounded model and tool metadata
    Given the production Matt Pocock extension and the observer load in one Pi v1 session
    When a real model turn starts, uses Matt Pocock tools, and ends
    Then evidence records Matt tool starts and ends, final text, usage, stop reason, branch state, active tools, and source IDs
    And evidence does not contain complete model context or tool result bodies
    And Matt start args include mode, capability, route, reference, action, and target fields
    And Matt results include mode, capability, route, passed, available, nodeCode, and normalized workflow state
    And matt_pocock_ask evidence includes bounded title, question, options, recommendation, timeout, and custom-answer fields
    And failed tool results include bounded error text for schema or execution diagnostics
    And context snapshots preserve the persisted workflow branch before a short or aborted turn ends

  Scenario: Fixed fixture checks run without arbitrary shell input
    Given the observer exposes fixture_checks with no parameters
    When the model calls fixture_checks
    Then it runs only node --test tests/verify.test.mjs and an optional fixed wizard bash -n check
    And it uses a restricted sandbox or reports unavailable without an unsafe fallback
    And sandbox self-checks prove Node can read the fixture while network and external reads are denied
    And the sandbox denies writes to the whole tests directory, including verify.test.mjs
    And the positive and negative probes require the sandbox process cwd to equal the real project root
    And failures expose bounded stdout and stderr diagnostics with exit, timeout, and abort state

  Scenario: Project file tools are confined to the real project
    Given the real project root contains a regular file, a parent escape, and a symlink candidate
    When read, write, edit, grep, find, or ls receives a path
    Then project paths are allowed and parent or symlink escapes are blocked before execution
    And writes and edits to tests/verify.test.mjs or its parent directories are immutable

  Scenario: Real-model observation has a bounded tool budget
    Given one real-model session is running
    When the fortieth tool call starts
    Then the observer records the limit once and aborts the current agent operation

  Scenario: Longer developer journeys have an explicitly bounded call allowance
    Given the default observer budget is 40 calls
    When a trusted journey catalog requests a larger finite allowance
    Then the observer accepts only integer budgets up to 80
    And invalid values fall back to 40 rather than disabling the bound

  Scenario: A later turn cannot bypass an exhausted session budget
    Given the observer has reached its tool allowance and aborted a turn
    When another turn attempts a tool call in the same session
    Then the observer blocks and terminates it before execution

  Scenario: Pi completion waits for the settled boundary
    Given Pi emits agent_end before a queued extension turn or automatic recovery finishes
    When the real-run harness waits before sending the next user message
    Then it continues collecting events until agent_settled
    And it does not close a still-running handoff turn
