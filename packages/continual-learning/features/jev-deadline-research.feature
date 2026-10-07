Feature: Measure Jev deadline sensitivity without changing learning authority
  Scenario: Compare the same known bilingual evidence
    Given a frozen public corpus with valid and invalid Harness candidates
    When five-second and fifteen-second arms run in alternating order
    Then model, questions, evidence, thresholds and retry policy remain identical
    And the exact wire request hashes must match across both arms
    And neither arm writes or applies a candidate

  Scenario: Preserve missing judgments separately from semantic errors
    Given a timeout or incomplete original response
    When quality and usage are summarized
    Then missing judgments are counted separately from completed false holds
    And unknown billable usage is not treated as free
    And forced offline responses are never reported as real inference quality

  Scenario: Require quality evidence before adopting a longer deadline
    Given complete original results from both arms
    When adoption eligibility is evaluated
    Then valid missed opportunities and incomplete judgments must decrease
    And unsafe accepts or newly held valid candidates prevent eligibility
    And one known corpus cannot establish heldout or whole-workflow improvement
