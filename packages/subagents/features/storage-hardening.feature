Feature: Private storage writes keep ownership boundaries

  Explicitly authorized private-storage writes preserve inode ownership and
  publish one owner-only regular file.

  Scenario: A hard-linked capability entry cannot overwrite its outside peer
    Given memory/lesson.md is a hard link to an outside file
    When the child replaces the lesson entry
    Then the append is refused
    And the outside file remains byte-identical

  Scenario: A hard-linked index cannot be overwritten
    Given memory/MEMORY.md is a hard link to an outside file
    When the bounded index is regenerated
    Then regeneration is refused
    And the outside file remains byte-identical

  Scenario: Proposal names remain unique under a timestamp collision
    Given two proposals with the same title are recorded in one millisecond
    When both writes complete
    Then both unaccepted candidate files remain
    And neither candidate overwrites the other

  Scenario: A hard-linked persisted definition cannot overwrite its outside peer
    Given the canonical agent.md destination is a hard link to an outside file
    When the explicitly authorized definition write runs
    Then persistence is refused
    And the outside file remains byte-identical

  Scenario: Migration refuses a hard-linked legacy source
    Given a legacy memory file is a hard link to an outside file
    When the explicitly approved migration is planned
    Then the plan is blocked before copying the linked bytes
    And the outside file remains byte-identical

  Scenario: An oversized proposal is refused before any local write
    Given a proposal whose complete UTF-8 file exceeds the 16 KiB Memory budget
    When the proposal is recorded
    Then it is refused before memory/proposals is created
    And no partial candidate is written

  Scenario: A proposal exactly at the UTF-8 budget is preserved
    Given a proposal whose complete serialized UTF-8 file is exactly 16 KiB
    When the proposal is recorded
    Then it succeeds
    And the candidate bytes are exactly 16 KiB with no truncation
