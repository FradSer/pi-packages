Feature: Native Pi utils package
  Adapt the Claude utils plugin into a native Pi package without Claude-only metadata.

  Scenario: Package exposes both utility skills
    Given the source utils plugin contains update-readme and update-changelog
    When the Pi package is inspected
    Then its manifest exposes the skills directory
    And both skills have SKILL.md files

  Scenario: Supporting references remain available
    Given each utility skill has a reference document
    When the skills are copied into the Pi package
    Then both reference documents remain beside their skill
    And the relative reference links resolve from each skill directory

  Scenario: Claude-only metadata is not shipped
    Given the source skills use Claude plugin frontmatter
    When the Pi package is inspected
    Then the manifest contains the pi-package keyword
    And it contains no Claude plugin manifest
    And skill frontmatter contains no Claude-only fields
    And skill instructions do not depend on CLAUDE_PLUGIN_ROOT
