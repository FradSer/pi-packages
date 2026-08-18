Feature: Research before modifying the code-context package
  To keep changes aligned with current Pi and retrieval integrations
  As a maintainer of @fradser/code-context
  I want package modifications to consult the applicable native context tools first

  Scenario: A Pi integration change consults current Pi documentation
    Given a change targets the code-context package
    And the change concerns Pi extension or package APIs
    When the maintainer starts implementation
    Then the maintainer uses context_context7 or context_deepwiki before editing

  Scenario: A retrieval-provider change consults the affected provider context
    Given a change targets a retrieval provider integration
    When the maintainer starts implementation
    Then the maintainer uses the native context tool for the affected provider when applicable
    And the maintainer records unavailable tools and uses a documented fallback

  Scenario: Unrelated changes do not require irrelevant lookups
    Given a change targets documentation or local tests only
    And it does not change Pi APIs or retrieval-provider behavior
    When the maintainer starts implementation
    Then the maintainer does not call unrelated context tools
