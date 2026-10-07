Feature: Native parent pipeline respects original Memory intent with fixed responses
  Scenario: A mixed batch passes only independent supported records
    Given native Pi loads the current parent with only its programmatic gate instrumented
    And fixed generation returns the same three original candidates in every arm
    And fixed SDK responses hold a permanent claim inferred from a temporary fault
    When the real explicit Memory command handler runs in isolated Linux Docker
    Then the real parent writes the two supported records to both roots
    And it preserves all three original candidates before writing
    And the pending candidate is counted separately
    And the following agent request receives only the applied Memory metadata
    And Harness and AGENTS.md are unchanged

  Scenario: Whole-plan semantics or service unavailability prevents writing
    Given the same original explicit Memory request and three candidates
    When the ordinary whole-plan path holds the batch or SDK transport is unavailable
    Then the native parent retains the original proposal without writing new Memory
    And it preserves the bound explicit request
    And no inferred permanent-failure Memory is injected into the following request

  Scenario: Evidence is categorized honestly
    Given main generation and SDK responses are fixed fixtures
    When native parent assertions pass
    Then the report proves execution and permission behavior
    And it does not claim real inference, recall-answer correctness or learning quality improvement

  Scenario: A timed out research runner cannot imply confirmed container cleanup
    Given container ownership is frozen before creation
    When the runner times out or creation completion is unknown
    Then the parent terminates its owned local process group
    And cleanup checks the declared owner, image, command and evidence mount
    And it reports daemon creation uncertainty instead of claiming final absence

  Scenario: Real Jev judgments are measured separately from fixed generation
    Given fixed public English and Chinese evidence and author-defined candidate labels
    When bounded real Jev calls drive the native parent
    Then the report measures valid writes, mistaken writes and valid held candidates
    And it records actual response model, known usage and unverified remote completion
    And it does not claim real main generation or independently established net quality improvement
