Feature: Research description counterevidence without weakening write guards
  Scenario: Preserve the original diagnosis
    Given an original description counter request and frozen evidence
    When constructing the research request
    Then original state, questions and criteria are unchanged
    And only two independent diagnostic Noul questions are added
    And neither result authorizes writes

  Scenario: Preserve uncertainty and conflict
    Given a conflicting fact, unresolved condition, invalid answer or missing response
    When interpreting the diagnostic answers
    Then uncertainty and failures remain holds
    And a low probability alone never overrides the original parent checks

  Scenario: Record only controlled diagnostics
    Given a response containing untrusted strings or extra fields
    When recording a research result
    Then only fixed labels and finite probabilities are retained
    And raw evidence and service text are absent
