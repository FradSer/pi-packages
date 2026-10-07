Feature: Bound composed Memory selection without write authority
  Scenario: Supported complete knowledge is independent of a held proposal
    Given complete original support and pair reviews
    And one candidate fails support verification
    When a complete bound standalone review confirms the supported candidate's full meaning
    Then the optional partition recovers only the supported candidate
    And returns no write permission

  Scenario: Existing behavior and selected-pair obligations remain mandatory
    Given no additional review or a stale, invalid or uncertain one
    When candidates are partitioned
    Then existing successful selections are preserved
    And no unsupported candidate is recovered
    And every pair in the initial tentative selection must still pass independence

  Scenario: Additional semantic answers cannot repair original invalid proofs
    Given missing original checks, citations, pair observations or frozen bindings
    When an additional standalone review is supplied
    Then no candidate is selected

  Scenario: Isolated parent collects complete standalone observations
    Given complete original support and pair checks and a programmatic composed gate
    When the judge reviews every candidate's body and description against full frozen originals
    Then bounded requests produce a bound diagnostic readiness review
    And the parent records its actual model, duration and fallback reason
    And only the original validated write transaction can apply a subset

  Scenario: Service failure preserves the original subset result
    Given a complete original relation review
    When extra standalone requests fail, change the dossier or return another model
    Then no additional readiness proof is produced
    And existing eligible indexes are preserved
