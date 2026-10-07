Feature: Research whether a supported new Memory can stand alone
  Scenario: An unrelated rejected candidate does not supply missing meaning
    Given a complete pnpm fact and a rejected permanent-failure inference
    When Jev judges the pnpm record with all other new records omitted
    Then the research observes whether its body and description remain complete
    And original candidate support and write permission remain separate requirements

  Scenario: A reference to another new record remains unsafe
    Given a body or description refers to a value or exception in another new record
    When the other record would not be written
    Then standalone readiness is not observed
    And uncertainty or missing context never becomes readiness

  Scenario: Other applied records still require pair validation
    Given more than one otherwise eligible record
    When a standalone observation succeeds
    Then it cannot override their conflict, redundancy or dependency review
    And this research performs no durable writes

  Scenario: Comparison remains frozen
    Given original English and Chinese evidence, candidates and labels frozen before inference
    When the original pair classifier and standalone classifier are evaluated
    Then thresholds, labels and original candidate bytes remain unchanged
    And unsupported writes, unsafe readiness, missed readiness and costs are reported separately
