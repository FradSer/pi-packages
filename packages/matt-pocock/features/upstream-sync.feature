Feature: Honest and isolated upstream verification
  Scenario: Synced content and checked tree share a commit
    Given upstream content has been synchronized to the latest checked commit
    When the synchronization checker validates the revision metadata
    Then it accepts the same commit for both revision roles

  Scenario: A comparison uses temporary metadata
    Given a temporary metadata file for a disposable upstream checkout
    When the checker receives --selection with that file
    Then it validates that selection without changing the workspace metadata

  Scenario: A new skill at the checked tree is classified
    Given the latest checked upstream tree adds an in-progress skill
    When the selection metadata is reviewed
    Then the new skill is excluded with a concrete reason and its upstream path

  Scenario: An unclassified skill fails the comparison
    Given a disposable upstream checkout with a skill missing from the selection
    When the synchronization checker compares that checkout
    Then it reports the unclassified skill and fails
