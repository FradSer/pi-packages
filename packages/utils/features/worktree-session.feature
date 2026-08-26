Feature: EnterWorktree and ExitWorktree session switching
  The utils package provides Claude Code-style worktree session switching.
  EnterWorktree creates or selects a git worktree, forks the current session into
  that worktree, and switches the Pi runtime to the worktree cwd. ExitWorktree
  returns to the parent session and offers cleanup for worktrees created by Pi.

  Background:
    Given the pi-utils-fradser package is installed

  Scenario: EnterWorktree creates a managed worktree and replacement session
    Given a persisted Pi session in the repository root
    When EnterWorktree is called with the name "feature-auth"
    Then a worktree is created at ".pi/worktrees/feature-auth"
    And a branch named "pi/worktree/feature-auth" is created
    And the replacement session cwd is the new worktree root
    And the replacement session records the original session as its parent

  Scenario: EnterWorktree enters an existing worktree without recreating it
    Given a persisted Pi session and an existing registered git worktree
    When EnterWorktree is called with that worktree path
    Then no new worktree or branch is created
    And the replacement session cwd is the existing worktree root

  Scenario: EnterWorktree switches directly between worktrees
    Given a Pi session already inside worktree A
    When EnterWorktree is called for worktree B
    Then the replacement session cwd is worktree B
    And ExitWorktree returns to worktree A before the original parent session

  Scenario: ExitWorktree returns to the parent session
    Given a Pi session entered through EnterWorktree
    When ExitWorktree is called and the worktree is kept
    Then Pi switches to the parent session
    And the worktree remains on disk

  Scenario: ExitWorktree can remove a clean worktree created by Pi
    Given a Pi session in a clean worktree created by EnterWorktree
    When the user chooses to remove the worktree during ExitWorktree
    Then the worktree and its Pi-created branch are removed
    And Pi switches to the parent session

  Scenario: ExitWorktree preserves dirty work by default
    Given a Pi session in a worktree with uncommitted changes
    When ExitWorktree is called and the user chooses to keep the worktree
    Then the worktree and its changes remain on disk
    And Pi switches to the parent session

  Scenario: EnterWorktree rejects an unregistered existing path
    Given a persisted Pi session in a git repository
    When EnterWorktree is called with a path that is not a registered git worktree
    Then the operation fails without creating a session or deleting files

  Scenario: EnterWorktree and ExitWorktree tools queue their session commands
    Given the Pi extension is loaded
    When the model calls EnterWorktree or ExitWorktree
    Then the tool queues the corresponding user command
    And the tool result reports that the transition is queued rather than complete

  Scenario: Worktree transition tools render compact started lifecycle rows
    Given the Pi extension is loaded in TUI mode
    When the model calls EnterWorktree or ExitWorktree
    Then each tool owns its shell rendering with an empty call row
    And each tool result renders one pi-kit worktree event row
    And the EnterWorktree row is `[worktree] enter · feature-auth`
    And the ExitWorktree row is `[worktree] exit · current worktree`
    And the row does not claim that the session transition is complete
