Feature: /git-agent command menu
  The git-agent workflows (commit, commit-and-push, init, related) are exposed
  as a native pi /git-agent menu, not as skills. Each menu item embeds its
  procedure inline via pi.sendUserMessage.

  Background:
    Given the @fradser/git-agent package is installed
    And package.json registers extensions only (no skills)

  Scenario: Menu lists all workflows
    When the user types /git-agent
    Then a select dialog shows Commit changes, Commit and push, Init / optimize, and Related files & tests

  Scenario: Selecting an item delivers the procedure inline
    Given the user picks "Commit changes"
    When the menu handler sends the follow-up message
    Then the message embeds procedures/commit.md verbatim
    And the message resolves {{PKG_DIR}} to the installed package dir

  Scenario: Keyword shorthand skips the menu
    When the user types "/git-agent commit --co-author \"Alice\""
    Then the commit workflow runs directly with invocation args "--co-author \"Alice\""

  Scenario: Natural language still routes without a skill
    When the user asks to "commit this"
    Then the agent follows procedures/commit.md (session_context first, then git-agent commit)

  Scenario: No skill surface remains
    Given the package tree
    Then there is no skills/ directory
    And no procedure references /skill:...
