Feature: Honest and isolated upstream verification
  Scenario: Synced content and checked tree share a commit
    Given upstream content has been synchronized to the latest checked commit
    When the synchronization checker validates the revision metadata
    Then it accepts the same commit for both revision roles

  Scenario: A comparison uses temporary metadata
    Given a temporary metadata file for a disposable upstream checkout
    When the checker receives --selection with that file
    Then it validates that selection without changing the workspace metadata
