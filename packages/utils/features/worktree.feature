Feature: git worktree path redirect
  The utils package restores the `git worktree add` path redirect: any bash
  command that runs `git worktree add` has its target path rewritten to live
  inside the repository's `.pi/worktrees/<name>`, so linked worktrees stay
  inside the repo instead of scattering sibling directories next to it. The
  bash tool runs in the session cwd, so a command issued from a subdirectory is
  rewritten to the absolute repository root rather than a path relative to
  wherever the shell happened to be.

  Background:
    Given the pi-utils-fradser package is installed

  Scenario: A `git worktree add` path is redirected into .pi/worktrees
    Given the agent runs `git worktree add ../foo feature/foo` at the repository root
    When the bash tool call is intercepted
    Then the command is rewritten to `mkdir -p .pi/worktrees && git worktree add .pi/worktrees/foo feature/foo`
    And the user is notified of the redirect

  Scenario: The redirect targets the repository root, not the shell directory
    Given the agent runs `git worktree add ../foo feature/foo` in a repository subdirectory
    When the bash tool call is intercepted
    Then the rewritten path is the absolute `<repo root>/.pi/worktrees/foo`
    And no `.pi` directory is created inside the subdirectory

  Scenario: An unignored managed directory is reported
    Given a repository that does not git-ignore `.pi/`
    When a worktree path is redirected
    Then the user is told to add `.pi/` to .gitignore or the worktree shows up as untracked
    And the extension does not edit the repository's .gitignore

  Scenario: Worktree redirect notifications use the shared Pi-kit notification adapter
    Given a git worktree add path is redirected
    When the extension notifies the user of that redirect
    Then it delegates notification sanitization and delivery to pi-kit

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
