Feature: Model-aware agent instruction authoring
  Scenario: Writing guidance includes the supplied skills and prompts article's core principles
    Given an author is writing skills, AGENTS.md, or task prompts
    When the writing-for-agents capability is loaded
    Then it teaches narrow skill descriptions and minimal routers
    And it replaces blanket reading and rigid recipes with contextual guidance
    And it audits stale instructions against the models used by contributors
    And it defines safe autonomy, approval boundaries, and end-to-end completion
