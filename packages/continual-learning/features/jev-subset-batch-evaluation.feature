Feature: Evaluate independent subsets against complete original batch judgments
  Scenario: A held batch contains independently supported candidates
    Given frozen synthetic sources and candidate labels captured before inference
    When actual Jev completes body, description, relationship and window checks
    And every original pair is evaluated without revealing expected labels
    Then count valid acceptance, erroneous acceptance and valid holds for both arms
    And preserve every original candidate as accepted or held
    And no candidate is written by the study

  Scenario: Whole-plan judgment already allows the batch
    Given the original complete judgment allows every candidate
    When the independent-subset research arm is compared
    Then retain the original whole-plan result without a new veto

  Scenario: A request fails or evidence is incomplete
    Given unavailable, timed out, malformed or mismatched judgments
    When the study records the attempt
    Then keep missing proof held rather than inferring independence
    And usage remains unknown where no complete usage was observed
    And offline preflight is never reported as inference quality
