Feature: git worktree path redirect
  The utils package restores the `git worktree add` path redirect: any bash
  command that runs `git worktree add` has its target path rewritten to live
  inside `.pi/worktrees/<name>`, so linked worktrees stay inside the repo
  instead of scattering sibling directories next to it.

  Background:
    Given the pi-utils-fradser package is installed

  Scenario: A `git worktree add` path is redirected into .pi/worktrees
    Given the agent runs `git worktree add ../foo feature/foo`
    When the bash tool call is intercepted
    Then the command is rewritten to `mkdir -p .pi/worktrees && git worktree add .pi/worktrees/foo feature/foo`
    And the user is notified of the redirect

  Scenario: A path already inside .pi/worktrees is left untouched
    Given the agent runs `git worktree add .pi/worktrees/foo feature/foo`
    When the bash tool call is intercepted
    Then the command is not rewritten

  Scenario: Options and positional arguments are preserved
    Given the agent runs `git worktree add --lock --reason "active task" -b feature/foo ../foo HEAD~1`
    When the bash tool call is intercepted
    Then `--lock` remains a flag without a value
    And `--reason "active task"` and `-b feature/foo` remain before the target path
    And the trailing `HEAD~1` is preserved after the target path

  Scenario: Quoted and escaped paths retain their shell meaning
    Given the agent runs `git worktree add "../feature branch" feature/foo`
    When the bash tool call is intercepted
    Then the target path is `.pi/worktrees/feature branch` as one shell argument
    And the quoted branch argument remains unchanged

  Scenario: Commands with unsupported shell syntax are left untouched
    Given the agent runs `git worktree add ../foo feature/foo && git status`
    When the bash tool call is intercepted
    Then the command is not rewritten

  Scenario: Non-worktree commands are left untouched
    Given the agent runs `git worktree list`
    When the bash tool call is intercepted
    Then the command is not rewritten
