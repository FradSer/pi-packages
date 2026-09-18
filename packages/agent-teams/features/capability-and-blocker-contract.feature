Feature: Honest capability grants and Work outcomes
  Scenario Outline: Public lifecycle results disclose the effective grant
    Given an Agent definition with <tools>
    When the Leader delegates or starts it and inspects the returned session
    Then model-visible results contain the recorded effective tool grant
    And coordination-only grants warn that file and shell work is unavailable
    And no execution tools are granted implicitly
    Examples:
      | tools                 |
      | omitted               |
      | an empty array        |
      | read and bash         |

  Scenario: Canonical capability guidance stays synchronized
    Given the canonical Worker tool universe including powershell
    When schema, Leader guidance, and unknown-Agent recovery are generated
    Then each includes all canonical built-in IDs without aliases

  Scenario: Inspection preserves historical capability evidence
    Given a resident with a recorded grant or a legacy unknown grant
    When the Leader inspects it after a role definition changes
    Then the recorded grant takes precedence and unknown is not reported as empty

  Scenario: Unknown Agent recovery names explicit minimal capabilities
    Given a Leader names an undefined Agent
    When delegation is rejected
    Then the error includes a compact inline definition example with canonical tool names
    And neither aliases nor additional permissions are introduced

  Scenario: A blocked Worker explicitly fails through the public Work tool
    Given current Work with a dependent Work Item
    When the Worker submits outcome failed with missing-capability evidence
    And execution settles repeatedly
    Then the Leader receives one failed report and no automatic success
    And the Work is not completed and its dependent remains blocked

  Scenario: Verification rejects a successful candidate
    Given current Work with an explicit verification gate and a dependent Work Item
    When a Worker submits success and the gate rejects its evidence
    Then neither completion nor dependent availability is granted

  Scenario: Guidance distinguishes successful candidates from blockers
    Given Worker and Leader guidance and the role template
    When the requested work cannot be performed
    Then the Worker is instructed to submit outcome failed rather than ordinary final prose
    And ungated acceptance is not described as independent verification
    And Leaders delegate concrete acceptance criteria and appropriate verification gates
    And informational reports need no acknowledgment unless decisions or actions change
