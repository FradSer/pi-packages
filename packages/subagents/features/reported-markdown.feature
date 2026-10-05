Feature: Markdown in reported agent answers
  Scenario: A final answer contains inline and block Markdown
    Given a complete result with headings, lists, bold, inline code and a fenced code block
    When the reported row renders and expands
    Then the answer uses native Markdown styles and block layout
    And each visible line fits the current width
    And the expanded answer appears once with native code block borders
    And the original result text and provenance remain unchanged

  Scenario: A short Markdown answer is fully visible
    Given a complete short bold answer
    When the row is collapsed
    Then its Markdown text is visible without raw bold markers
    And it has no expansion hint unless rendering hides content
