Feature: Real model memory improves held-out task outcomes
  Scenario: Paired follow-up tasks have no training transcript leakage
    Given frozen synthetic learning evidence and an independent expected answer
    When the same real model runs fresh sessions with learned Memory and without Memory
    Then both sessions receive identical current task and repository evidence
    And only the treatment can retrieve the actual parent-applied Memory
    And scores depend on the written task artifact, not planner claims

  Scenario: Incorrect or bounded knowledge does not become future authority
    Given uncertain claims, one-task instructions, conflicting decisions, expired facts and explicit corrections
    When a fresh follow-up task requests the current fact
    Then uncertainty is retained and current authoritative evidence wins
    And corrected knowledge replaces the old answer
    And memory regressions and learning failures remain visible in the report

  Scenario: Reading Memory cannot accidentally overwrite learned knowledge
    Given ordinary tasks can read learned entries as untrusted references
    When a model uses write or edit on a private or shared Memory entry root
    Then the call is refused and directs maintenance through the parent-owned Memory workflow
    And ordinary project output writes remain available

  Scenario: Empty Memory discovery does not invite guessed retrieval
    Given there are no available established project entries with or without an empty index
    When a fresh task starts with automatic learning disabled
    Then it receives an explicit empty Memory reference
    And fixed instructions constrain discovery to supplied Memory locations
    And the absence of Memory does not authorize guessing a project fact

  Scenario: A correction can carry the evidence required by parent validation
    Given a selected existing Memory and a later original user correction
    When the learner proposes a cited rewrite or delete
    Then the incremental parser retains the bounded original evidence
    And initial and repaired plans pass through the same citation validation
    And assistant claims or absent citations cannot authorize a rewrite
