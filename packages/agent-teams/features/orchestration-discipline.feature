Feature: Candidate-bound Agent orchestration
  The Leader owns integration and final acceptance.
  Guidance coordinates existing Work primitives without adding runtime authority.

  Scenario: Idle and active Leaders receive the same completion discipline
    Given Agent Teams is loaded with or without active Work
    When the Leader prompt is assembled
    Then it assigns local verification to implementers and integrated verification to one owner
    And it keeps completion pending until required Work and blocking reviews have returned
    And it distinguishes a completed review Work Item from a PASS verdict on the implementation
    And if only required results remain outstanding it yields without declaring the task complete

  Scenario: Delegation declares dependencies and a safe verification boundary
    Given parallel Work may share files or depend on a changing shared module
    When the Leader prepares assignments
    Then each assignment names its scope, baseline, acceptance criteria and safe local checks
    And dependent Work is serialized or represented by dependsOn before assignment
    And conflicting writes use shared resource tags rather than overlapping ownership
    And verification safety is established before commands run
    And verify is described as an independent reviewer prompt rather than a shell command

  Scenario: Review and verification judge the same integrated candidate
    Given implementers have delivered their locally checked changes
    When the Leader starts blocking review and integration checks
    Then both refer to the same recorded candidate and task-scoped baseline
    And unrelated dirty work is excluded from the review diff
    And changing the candidate invalidates affected review or verification evidence
    And an earlier result is not presented as proof of a later candidate

  Scenario: Findings are repaired by cause and rechecked through existing Work
    Given a completed review reports related counterexamples
    When the Leader plans corrections
    Then it groups them by root cause and adds adjacent-case regressions before retesting
    And it prepares a refreshed candidate brief before assigning the bounded recheck
    And it reopens completed review Work only when its description already references that authoritative brief
    And a fixed conflicting description uses bounded follow-up Work depending on the completed review instead
    And it does not message a closed assignment to restart review
    And it creates a new broad review only when scope or risk materially changes
    And it retains the existing release and assignment authority for unfinished Work

  Scenario: Workers report bounded evidence rather than global completion
    Given an implementer or reviewer is assigned one Work Item
    When it returns its result
    Then it identifies the inspected candidate, checks, findings and limitations
    And it runs only the assigned verification scope unless the Leader changes that scope
    And a successful review assignment may report REWORK without claiming implementation acceptance
    And a review-only Worker returns its report without editing or waiting for repairs
    And inability to perform the review uses an explicit failed submission

  Scenario: Reopen does not carry a refreshed review brief implicitly
    Given a completed review records a fixed candidate description and prior findings
    When the Leader needs to review a repaired candidate
    Then the prior report is preserved before reopening could clear its result
    And the refreshed brief includes the retained baseline, new candidate fingerprint, correction delta, prior findings and safe checks
    And neither reopen nor its reason rewrites the task description or automatically forwards the prior findings
    And the assigned reviewer reads and validates the authoritative brief before inspecting the candidate
