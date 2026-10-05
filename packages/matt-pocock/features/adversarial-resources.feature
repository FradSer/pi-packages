Feature: Matt Pocock resource boundaries survive adversarial state

  Scenario: Historical delivery aliases do not duplicate procedure bodies
    Given a persisted delivery set contains aliases, duplicates, and unknown ids
    When the active procedure delta is resolved
    Then only canonical catalog procedures are considered delivered

  Scenario: Legacy workflow state without delivery tracking remains usable
    Given a workflow record from before delivery tracking existed
    When it transitions and resolves its next procedure
    Then the missing delivery set is backfilled without throwing

  Scenario: UTF-8 procedure bundles enforce the byte boundary exactly
    Given an isolated temporary catalog copy has a multibyte body at the limit
    When its bundle is resolved at and above the limit
    Then the exact limit succeeds and the larger bundle is rejected

  Scenario: The catalog-derived resource graph keeps every public edge safe
    Given the current catalog manifest defines all bundled procedures and workflow edges
    When every resource closure, alias, disclosure and transition is exercised in one batch
    Then legal edges resolve and illegal transitions leave the state unchanged

  Scenario: A corrupted phase cannot migrate a workflow
    Given a workflow record has a valid route and procedure but an unrelated phase
    When a transition is requested
    Then the migration is rejected before changing procedure state
