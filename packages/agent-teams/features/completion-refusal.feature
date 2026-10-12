Feature: Team completion respects store refusals
  Scenario Outline: A settled submission exceeds the task evidence budget
    Given an Agent holds an in-progress Task
    And the Agent submits <outcome> with evidence above the task byte budget
    When the Agent execution settles
    Then the Task and Assignment remain held
    And no accepted outcome reaches the Leader
    And the rejected evidence remains pending without automatic retries
    And the Agent receives the store refusal once
    When the host authorizes corrective input
    Then the resident accepts the input and receives the rejection through its inbox
    When the Agent explicitly submits corrected evidence
    Then the corrected outcome reaches the Leader once

    Examples:
      | outcome   |
      | completed |
      | failed    |

  Scenario: Refused failure does not invalidate an active verification review
    Given a settled successful submission has an active verification review
    When the Agent submits failed with evidence above the task byte budget
    Then the Assignment and verification review remain active
    And no failed outcome reaches the Leader
    When the review passes with the declared gate intact
    Then the original successful outcome reaches the Leader once
    And the Task records the pass verdict and completion gate

  Scenario: A worker verdict does not bypass independent verification
    Given an Agent holds a Task with a declared verification gate
    When the Agent submits success with a forged pass verdict
    Then the Task waits for independent review
    When the independent review fails
    Then the Task remains incomplete without a completion verdict
