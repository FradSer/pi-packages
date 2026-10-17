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
    And the redirect notice names that absolute directory, not a relative spelling
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

  Scenario: A successful redirected creation moves the session into the new worktree
    Given the agent runs `git worktree add ../foo feature/foo` at the repository root
    And the session has a persisted session file
    When the bash command succeeds
    Then the rest of the tool batch is blocked before execution
    And the session switches to `.pi/worktrees/foo` when the turn settles
    And the user is told the created worktree is where this session moves
    And the replacement session records the entered-worktree row for that directory
    And the worktree is entered as an existing worktree, so no second worktree is created

  Scenario: A failed redirected creation leaves the session in its checkout
    Given the agent runs a redirected `git worktree add` that git rejects
    And the session has a persisted session file
    When the bash command fails
    Then the session stays in its current directory
    And the blocked tool batch is released for retry
    And the user is told the worktree was not created

  Scenario: A reserved creation that produces no result never moves the session
    Given a redirected creation reserved the session move
    When the bash call ends without a result, for example a truncated message or a blocker
    Then no session switch is dispatched
    And the user is told the command produced no result and the session did not move

  Scenario: A session that starts releases a pending transition
    Given a redirected creation reserved the session move
    When a replacement session starts before that transition is applied
    Then the barrier is released and later tools run again
    And no session switch is dispatched

  Scenario: A creation cannot start while another switch is in flight
    Given a worktree switch is already in flight
    When the model requests a redirected `git worktree add`
    Then the bash call is blocked before execution
    And no worktree is created
    And the block reason names the switch in progress

  Scenario: A queued creation refuses a newer switch
    Given a redirected creation reserved the session move
    When a worktree command is invoked before that turn settles
    Then the command is refused with a warning naming the queued transition
    And the reserved creation still moves the session at settlement

  Scenario: A session without a session file cannot move
    Given the agent runs a redirected `git worktree add` in a session without a session file
    When the bash command succeeds
    Then the worktree is created
    And the tool batch is not blocked
    And the user is told this session cannot switch to the created worktree
    And no entered-worktree row is recorded

  Scenario: Only a rewritten creation requests the move
    Given the agent runs `git worktree add ../foo feature/foo && git status`
    When the bash tool call is intercepted
    Then the command is not rewritten
    And the session does not move

  Scenario: An explicit transition wins over the automatic move
    Given one model message requests EnterWorktree together with a redirected `git worktree add`
    When the batch is prepared
    Then only the explicit transition is queued
    And the automatic move is refused

  Scenario: An aborted run drops the automatic move
    Given a redirected creation succeeded and the automatic move is queued
    When the user aborts the run
    Then no session switch starts
    And the user is told the automatic move was dropped
    And the created worktree remains on disk
