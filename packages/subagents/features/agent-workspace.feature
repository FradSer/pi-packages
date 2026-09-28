Feature: Durable per-Agent workspaces

  Pi stores sessions under the agent directory grouped by working directory, and
  `--continue` opens the most recent session for the current working directory.
  The working path is therefore the memory key: a stable workspace per Agent is
  what makes Pi's own session storage usable as that Agent's working memory, with
  Pi's compaction, branching, `/resume` picker, and `/export` doing the work a
  bespoke scheme would have to rebuild.

  This is why a workspace is durable and per-Agent rather than per-task and
  disposable. A per-task worktree that is removed on completion orphans its
  session group every attempt, which is fragmentation that looks like amnesia and
  also accumulates storage without bound.

  Rule: The workspace is durable and stable per Agent and project

    Scenario: The same Agent in the same project always resolves one path
      Given an Agent name and a project working directory
      When the workspace path is resolved twice
      Then both resolutions are identical
      And the path is under the agent directory, not inside the checkout

    Scenario: Different Agents and different projects get different homes
      Given one Agent in two projects, and two Agents in one project
      When the workspace paths are resolved
      Then all three differ

    Scenario: The first attempt creates and the second reuses
      Given a repository with at least one commit
      When an isolated workspace is ensured twice for the same Agent
      Then the first creates a linked worktree on a durable per-Agent branch
      And the second reports reuse and the same working directory
      And reuse is what preserves the Agent's Pi session group

  Rule: Falling back to a shared tree is reported, never pretended

    Scenario: A shared isolation request uses the caller's directory
      Given isolation is explicitly shared
      When the workspace is ensured
      Then the working directory is the caller's
      And isolation is reported as none

    Scenario: A working directory that is not a repository cannot be isolated
      Given a working directory that is not a git repository
      When an isolated workspace is ensured
      Then the caller's directory is used
      And a reason states that it is not a git repository
      And nothing claims the child was isolated

  Rule: Completion preserves; only an explicit release removes

    Scenario: Preserving commits attempt output and keeps the directory
      Given a workspace holding an uncommitted file
      When the workspace is preserved
      Then the file is committed onto the Agent's durable branch
      And the directory still exists afterwards
      And an interrupted or crashed attempt therefore still leaves its work retrievable

    Scenario: Preserving a clean workspace is not an error
      Given a workspace with no uncommitted changes
      When the workspace is preserved
      Then it reports success with nothing committed

    Scenario: Release removes the directory but keeps the branch
      Given an existing workspace
      When it is released explicitly
      Then the directory is gone
      And the durable branch survives so preserved work stays retrievable

    Scenario: A failed spawn never removes a workspace it did not create
      Given a spawn that fails after reusing an existing workspace
      When the failure path discards the workspace
      Then the reused workspace is left untouched
      And only a workspace this spawn created, in which nothing ran, may be removed

  Rule: Write isolation is a separate layer and is not claimed here

    Scenario: A worktree separates the filesystem without confining writes
      Given an Agent granted bash inside its workspace
      When the isolation it receives is described
      Then it is filesystem separation through a linked worktree
      And no kernel write confinement is claimed, because none is implemented
