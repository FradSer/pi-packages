Feature: git worktree path redirect
  The utils package restores the `git worktree add` path redirect: any bash
  command that runs `git worktree add` has its target path rewritten to live
  inside `.pi/worktrees/<name>`, so linked worktrees stay inside the repo
  instead of scattering sibling directories next to it.

  Background:
    Given the @fradser/utils package is installed

  Scenario: A `git worktree add` path is redirected into .pi/worktrees
    Given the agent runs `git worktree add ../foo feature/foo`
    When the bash tool call is intercepted
    Then the command is rewritten to `mkdir -p .pi/worktrees && git worktree add .pi/worktrees/foo feature/foo`
    And the user is notified of the redirect

  Scenario: A path already inside .pi/worktrees is left untouched
    Given the agent runs `git worktree add .pi/worktrees/foo feature/foo`
    When the bash tool call is intercepted
    Then the command is not rewritten

  Scenario: Flags and extra positional arguments are preserved
    Given the agent runs `git worktree add -b feature/foo ../foo HEAD~1`
    When the bash tool call is intercepted
    Then the rewritten command keeps `-b feature/foo` before the target path
    And the trailing `HEAD~1` is preserved after the target path

  Scenario: Non-worktree commands are left untouched
    Given the agent runs `git worktree list`
    When the bash tool call is intercepted
    Then the command is not rewritten
