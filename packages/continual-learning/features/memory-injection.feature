Feature: Auto-memory injects an index, not full entries

  Project memory keeps per-entry files. The leader prompt only carries a
  bounded index of filenames with one-line descriptions; the full content of
  a memory is read on demand. (ADR 0003)

  Scenario: The system prompt carries the memory index without entry bodies
    Given memory entries with frontmatter descriptions and multi-paragraph bodies
    When the memories block is formatted for the system prompt
    Then it lists each entry once with filename, source, and description
    And it contains no entry body text
    And it tells the model to read a memory file when its description is relevant

  Scenario: The index is bounded at entry boundaries
    Given more memory entries than the index budget allows
    When the memories block is formatted
    Then whole entries are dropped at the budget boundary instead of truncated mid-line
    And the budget is an index budget, not a full-text budget

  Scenario: Entries without a description still appear in the index
    Given a memory entry with no description in its frontmatter
    When the memories block is formatted
    Then the index line lists the filename and source without a description
