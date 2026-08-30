Feature: git worktree-aware @ completions
  The utils package filters editor file suggestions so a pi session only sees
  paths that belong to its own git worktree. A session in main never suggests
  linked worktree contents, and a session inside a linked worktree never
  suggests sibling worktrees or the main checkout.

  Background:
    Given the pi-utils-fradser package is installed

  Scenario: Main checkout hides linked worktree paths
    Given a git repository with a linked worktree at wt-b
    And a pi session running in the repository root
    When the built-in provider suggests "../wt-b/src/index.ts"
    Then the suggestion is dropped

  Scenario: Main checkout hides .pi/worktrees directory and its contents
    Given a git repository with or without linked worktrees
    And a pi session running in the repository root
    When the built-in provider suggests ".pi/worktrees", ".pi/worktrees/", or ".pi/worktrees/foo/src/index.ts"
    Then all of those suggestions are dropped

  Scenario: A linked worktree hides sibling worktrees, parent worktrees dir, and the main checkout
    Given a git repository with linked worktrees at .pi/worktrees/foo and .pi/worktrees/bar
    And a pi session running inside .pi/worktrees/foo
    When the built-in provider suggests "../../README.md", "../bar/src/index.ts", or "../../.pi/worktrees"
    Then all of those suggestions are dropped

  Scenario: Own worktree paths stay visible
    Given a pi session running inside a linked worktree
    When the built-in provider suggests "src/index.ts"
    Then the suggestion is kept

  Scenario: Quoted and @-prefixed values are filtered like plain paths
    Given a session in main with a linked worktree at .pi/worktrees/foo
    When the provider suggests '@".pi/worktrees/foo/src/index.ts"'
    Then the suggestion is dropped

  Scenario: Absolute candidate paths resolve before filtering
    Given a pi session running inside a linked worktree
    When the provider suggests an absolute path under the main checkout
    Then the suggestion is dropped

  Scenario: Directory entries of foreign roots are dropped too
    Given a session in main with a linked worktree at .pi/worktrees/foo
    When the provider suggests ".pi/worktrees/foo/"
    Then the suggestion is dropped

  Scenario: Non-git directories disable filtering
    Given a session running outside any git repository
    When the provider returns suggestions
    Then every suggestion is kept unchanged

  Scenario: A session opened in a bare repository filters its linked worktrees
    Given a bare repository acting as the shared store for linked worktrees
    And a pi session running at the bare repository path
    When the provider suggests a path inside one of the linked worktrees
    Then the suggestion is dropped

  Scenario: Worktree discovery happens once per session
    Given a pi session running in a git repository
    When several completion rounds run in the same session
    Then the git worktree list command runs at most once

  Scenario: Filtering follows session replacement into a worktree
    Given a git repository with a linked worktree at .pi/worktrees/foo
    And a pi session that started in the repository root
    When the session is replaced into .pi/worktrees/foo and the provider suggests "../README.md"
    Then the suggestion is dropped

  Scenario: Filtering stays outermost when another @ provider is installed later
    Given a git repository with linked worktrees under .pi/worktrees
    And a later @ provider returns both package and .pi/worktrees suggestions
    When the provider suggests paths while a session runs in the repository root
    Then suggestions inside .pi/worktrees are dropped
