Feature: /git command menu
  The GitFlow workflows (start/finish feature/hotfix/release, commit,
  commit-and-push) are exposed as a native pi /git menu, not as skills. Each
  menu item embeds its procedure inline via pi.sendUserMessage, with
  {{WORKFLOW_TYPE}} substituted by the menu handler.

  Background:
    Given the @fradser/git package is installed
    And package.json registers extensions only (no skills)
    And the package stays decoupled (no references to the AI commit CLI package)

  Scenario: Menu lists all workflows
    When the user types /git
    Then a select dialog shows Start/Finish for feature, hotfix, release, plus Commit changes and Commit and push

  Scenario: Start/finish procedures receive the workflow type
    Given the user picks "Start hotfix"
    When the menu handler sends the follow-up message
    Then the message embeds procedures/start.md with {{WORKFLOW_TYPE}} = hotfix
    And the start pipeline reference resolves via {{PKG_DIR}}

  Scenario: Keyword shorthand skips the menu
    When the user types "/git finish-release 1.3.0"
    Then the finish workflow runs directly with invocation args "1.3.0"

  Scenario: No skill surface remains
    Given the package tree
    Then there is no skills/ directory
    And references contain no /skill: references and no unsubstituted {{...}} placeholders
