Feature: /github command menu
  The GitHub workflows (create-issues, create-pr, resolve-issues, review-pr)
  are exposed as a native pi /github menu, not as skills. Each menu item
  embeds its procedure inline via pi.sendUserMessage; the create-pr procedure
  remains the plugin's only PR-creating path.

  Background:
    Given the @fradser/github package is installed
    And package.json registers extensions only (no skills)
    And reference docs ship under references/ with per-workflow symlinks to references/shared/

  Scenario: Menu lists all workflows
    When the user types /github
    Then a select dialog shows Create issue(s), Create pull request, Resolve issue(s), and Review PR

  Scenario: Selecting an item delivers the procedure inline
    Given the user picks "Create pull request"
    When the menu handler sends the follow-up message
    Then the message embeds procedures/create-pr.md verbatim
    And reference paths resolve through {{PKG_DIR}}

  Scenario: Keyword shorthand skips the menu
    When the user types "/github review-pr 123 --auto-merge"
    Then the review-pr workflow runs directly with invocation args "123 --auto-merge"

  Scenario: PR creation always hands off to review
    When the create-pr workflow completes
    Then it continues with the review-pr procedure (unless --no-monitor or explicit opt-out)
    And no workflow calls gh pr create outside create-pr

  Scenario: Natural language still routes without a skill
    When the user asks to "create a PR"
    Then the agent follows procedures/create-pr.md (quality gate, then review loop)

  Scenario: No skill surface remains
    Given the package tree
    Then there is no skills/ directory
    And no procedure references /skill:...
    And every per-workflow reference symlink resolves
