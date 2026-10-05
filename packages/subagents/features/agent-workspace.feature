Feature: Ordinary durable Agent data homes

  Every disk identity has private Memory, ordinary scratch and project-scoped
  history under the configured agent directory. The child edits the original
  project cwd; scratch is neither a checkout nor write confinement.
  VISION.md replaces all linked-worktree, preserve and release behavior.

  Rule: Path helpers are read-only and do not imply identity

    Scenario: One identity has one home and one scratch directory across projects
      Given an Agent name and two project directories
      When its home and workspace paths are calculated
      Then they are under agents/name in the configured agent directory
      And both projects use the same scratch directory
      And nothing is created on disk

    Scenario: Project histories remain private and distinct
      Given two Agents and two project directories
      When their session paths are calculated
      Then each history uses agents/name/projects/project-slug/session
      And the existing stable projectSlug algorithm is preserved
      And none uses the parent Pi session store

  Rule: Parent sessions own separate project histories

    Scenario: Different parent session IDs hash to distinct stable histories
      Given one Agent, one project directory and two non-empty opaque parent session IDs
      When their session paths are calculated with each parent ID
      Then each path uses projects/project-slug/parents/parent-sha256/session
      And the raw parent IDs never occur in either path
      And repeating one parent ID returns the same path while the other path differs

    Scenario: Omitting a parent session ID preserves the legacy history path
      Given one Agent and one project directory
      When a session path is calculated without a parent session ID
      Then it remains projects/project-slug/session
      And no directory is created

    Scenario: Blank parent session IDs are refused before provisioning
      Given one Agent, one project directory and a blank parent session ID
      When durable data is provisioned with that ID
      Then it is refused before any Agent directory is created

    Scenario: Oversized parent session IDs are refused before provisioning
      Given one Agent, one project directory and a parent session ID over 4 KiB in UTF-8
      When durable data is provisioned with that ID
      Then it is refused before any Agent directory is created

    Scenario: A new parent session does not import legacy project history
      Given an existing legacy project session directory and history file
      When durable data is provisioned with a new parent session ID
      Then the new session directory is distinct
      And the legacy directory and its bytes remain unchanged

  Rule: Provisioning builds ordinary directories, never a Git workspace

    Scenario: First provision creates durable data and second provision reuses it
      Given a valid disk identity authorized by its caller
      When ensureAgentWorkspace is called twice
      Then the first reports reused false and the second reports reused true
      And each returns cwd, workspacePath, sessionDir and reused only
      And cwd is the original project path, not scratch
      And memory/MEMORY.md, memory/proposals, workspace and project history exist
      And no Git command, branch, commit or worktree is used

    Scenario: An existing memory index and scratch output survive provisioning
      Given an existing MEMORY.md index and scratch output
      When durable data is provisioned for another project
      Then their bytes remain unchanged
      And state.json preserves createdAt and updates lastProject and memoryEntryCount
      And state.json is published atomically
      And every state writer uses the same exclusive update boundary
      And unrecognized metadata and a pre-existing lock are never overwritten
      And no user-scope definition is synthesized

    Scenario: Invalid names, unsafe destinations and disguised worktrees are refused
      Given a traversal name, symlinked durable path, malformed state or scratch with .git
      When durable data is provisioned
      Then it is refused instead of following or disguising the unsafe path
      And existing output and metadata remain unchanged

    Scenario: Unsafe session files cannot escape private history
      Given the private project session directory contains a jsonl symlink or hard link
      When an Agent provisions or resumes history
      Then startup is refused before a child can read or append to that history
      And the linked outside history remains byte-identical
      And a directory or non-regular jsonl entry is not treated as saved history

    Scenario: Provisioning does not require a repository
      Given an ordinary project directory without Git metadata
      When durable data is provisioned
      Then it succeeds and the child still uses that original project directory

    Scenario: Parallel provisioners preserve the identity creation timestamp
      Given multiple isolated processes provisioning one identity
      When their atomic state writes complete
      Then state.json remains parseable with the same creation timestamp
      And no temporary file remains after successful publication
