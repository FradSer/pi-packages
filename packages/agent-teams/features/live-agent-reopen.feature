@live @opt-in
Feature: Native worker terminal report and direct assignment reopen
  Scenario: A real provider completes two distinct assignments in one resident
    Given PI_PROVIDER and PI_MODEL explicitly select an authenticated live provider
    And a temporary session starts a report-only resident through spawnTeammate
    When its first assignment-tagged completed report reaches the leader callback
    And the callback immediately reopens a second assignment through sendLeaderMessage
    Then the same resident returns the second assignment-tagged completed report
    And the assignment IDs are distinct and match their accepted mailbox events
    And LIVE_AGENT_REOPEN_OK is emitted only after both reports are verified
    And the harness tears down the resident and temporary files even on failure
