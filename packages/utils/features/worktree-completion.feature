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

  Scenario: A session cannot read a foreign worktree directly
    Given a git repository with a linked worktree at .pi/worktrees/foo
    And a pi session running in the repository root
    When the read tool is called for ".pi/worktrees/foo/src/index.ts"
    Then the read is blocked
    And its result tells the agent to use enter_worktree before reading

  Scenario: A session can read files in its own worktree
    Given a pi session running inside .pi/worktrees/foo
    When the read tool is called for "src/index.ts"
    Then the read is allowed

  Scenario: A linked worktree hides sibling worktrees, parent worktrees dir, and the main checkout
    Given a git repository with linked worktrees at .pi/worktrees/foo and .pi/worktrees/bar
    And a pi session running inside .pi/worktrees/foo
    When the built-in provider suggests "../../README.md", "../bar/src/index.ts", or "../../.pi/worktrees"
    Then all of those suggestions are dropped

  Scenario: Own worktree paths stay visible
    Given a pi session running inside a linked worktree
    When the built-in provider suggests "src/index.ts"
    Then the suggestion is kept

  Scenario: A linked worktree nested inside another checkout keeps its own files
    Given a git repository with a linked worktree at "vendor/wt"
    And a pi session running inside "vendor/wt"
    When the built-in provider suggests "src/index.ts" or its absolute path
    Then both suggestions are kept
    And the read, edit, and write tools are allowed for them

  Scenario: A nested linked worktree is still foreign to the checkout containing it
    Given a git repository with a linked worktree at "vendor/wt"
    And a pi session running in the repository root
    When the built-in provider suggests "vendor/wt/src/index.ts"
    Then the suggestion is dropped
    And the read tool is blocked for that path

  Scenario: A worktree inside the managed directory is never exempted early
    Given linked worktrees at ".pi/worktrees/parent" and ".pi/worktrees/parent/vendor/wt"
    And a pi session running inside ".pi/worktrees/parent"
    When the provider suggests "vendor/wt/file.txt" or an absolute path inside it
    Then those suggestions are dropped
    And the session's own files stay visible
    And a stale directory in the managed directory is still hidden

  Scenario: A search result line names a foreign path containing a space
    Given a foreign worktree whose path contains a space
    When a search tool returns "<foreign path>/src/index.ts:1: content"
    Then that line is dropped
    And a local path line and a no-match line are kept

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

  Scenario: fffind excludes foreign worktree and managed worktree results
    Given a git repository with a linked worktree at .pi/worktrees/foo
    And a pi session running in the repository root
    When fffind or find returns paths containing ".pi/worktrees/foo/src/index.ts"
    Then the foreign worktree paths are filtered from the tool result

  Scenario: ffgrep excludes foreign worktree and managed worktree results
    Given a git repository with a linked worktree at .pi/worktrees/foo
    And a pi session running in the repository root
    When ffgrep or grep matches content in ".pi/worktrees/foo/src/index.ts"
    Then the foreign worktree matches are filtered from the tool result

  Scenario: fffind and ffgrep tool calls automatically exclude foreign worktrees
    Given a git repository with a linked worktree at .pi/worktrees/foo
    And a pi session running in the repository root
    When fffind or ffgrep tool is called without exclude
    Then the foreign worktree pattern is added to exclude

  Scenario: A search tool that does not declare exclude is never given one
    Given a search tool owned by another package whose schema has no exclude parameter
    When that tool is called without exclude
    Then its input is left untouched
    And its result text is still filtered of foreign worktree paths

  Scenario: A session opened in a bare repository filters its linked worktrees
    Given a bare repository acting as the shared store for linked worktrees
    And a pi session running at the bare repository path
    When the provider suggests a path inside one of the linked worktrees
    Then the suggestion is dropped

  Scenario: Worktree discovery is memoized and refreshed when the list changes
    Given a pi session running in a git repository
    When several completion rounds run with an unchanged worktree list
    Then the git worktree list command runs at most once
    When a worktree is added or removed during the session
    Then the next round discovers it without hiding the new worktree

  Scenario: Search results are resolved against the search tool's own root
    Given a pi session in main and a linked worktree elsewhere
    When a search whose root is that worktree returns "src/index.ts:1: content"
    Then the line is dropped as foreign
    When the same search runs with the session's own root
    Then the line is kept

  Scenario: A retargeted symlink cannot keep its old identity
    Given a symlink inside the session's checkout that pointed at a local file
    When it is retargeted into a linked worktree
    Then the read, edit, and write tools block it

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
