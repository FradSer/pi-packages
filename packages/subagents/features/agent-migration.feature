Feature: Explicit copy-only legacy Agent migration

  Migration is an authorized library operation, never a tool or discovery side
  effect. Plans record source and destination hashes; originals remain unchanged.

  Rule: Planning and dry-run are read-only

    Scenario: Plan one legacy user identity and its durable data
      Given agents/reviewer.md with deprecated persistence and isolation fields
      And legacy entry files, MEMORY.md and proposals under agents/reviewer
      And legacy subagent-sessions/reviewer/project history
      When planAgentMigration and applyAgentMigration dry-run are called
      Then the plan maps the definition to agents/reviewer/agent.md
      And memory files map to agents/reviewer/memory
      And sessions map to agents/reviewer/projects/project/session
      And no destination, directory, state or definition is created
      And source hashes and body bytes are preserved

    Scenario: Apply an explicitly approved plan
      Given a current conflict-free plan
      When applyAgentMigration is explicitly called
      Then new files are exclusively created from the approved source bytes
      And deprecated frontmatter is removed without changing the Markdown body
      And name, description, tools, model, verify and body retain their parsed meaning
      And supported field lines and valid UTF-8 body bytes retain their authored bytes and line endings
      And every original file remains byte-identical
      And migration neither starts a process nor creates a user promotion

  Rule: Canonicalization must be lossless for supported definition content

    Scenario Outline: Preserve the parser's whitespace and tools variants
      Given a valid legacy definition with <whitespace> around field keys
      And <tools> tools and LF, CRLF or mixed header line endings
      And deprecated fields with whitespace before the colon and list values
      When an explicitly approved migration is applied
      Then the actual definition parser gives identical supported fields and body before and after
      And each supported field line and the Markdown body stays byte-identical
      And deprecated fields and their list values are removed
      And no authored tools field is replaced with an empty default

      Examples:
        | whitespace       | tools       |
        | spaces           | comma list  |
        | tabs             | inline list |
        | spaces and tabs  | block list  |

    Scenario: Missing legacy defaults remain explicit
      Given a legacy definition with a name and body but no description or tools
      When an explicitly approved migration is applied
      Then description and tools default to empty values
      And the authored body bytes are unchanged

    Scenario Outline: Refuse unsupported duplicate frontmatter fields
      Given a legacy definition with two <field> keys even when their colon whitespace differs
      When migration is planned
      Then the plan is blocked with an invalid duplicate-field diagnostic naming the source
      And apply refuses without creating any destination
      And all source bytes remain unchanged

      Examples:
        | field       |
        | name        |
        | description |
        | tools       |
        | model       |
        | verify      |
        | memory      |

    Scenario: Refuse defaults that change authored field semantics
      Given a CRLF definition with tools missing and a trailing comment on its last description line
      When migration is planned
      Then the plan is blocked if making tools explicit would change the authored description meaning
      And missing defaults never authorize changes to any authored supported field
      And all source bytes remain unchanged and no destination is created

    Scenario: Refuse filtering that changes runtime parser semantics
      Given a CRLF definition with a trailing comment on verify before a deprecated field
      And dropping the deprecated field would change the actual parser's verify value
      When migration is planned
      Then the plan is blocked with an invalid semantic-change diagnostic naming the source
      And apply refuses without rewriting supported bytes or creating any destination
      And diagnostics contain no private body content

    Scenario: Refuse definition bytes that cannot round-trip through UTF-8
      Given a legacy definition whose body contains invalid UTF-8 bytes
      When migration is planned
      Then the plan is blocked with an invalid UTF-8 diagnostic naming the source
      And apply refuses without normalizing or replacing any invalid byte
      And diagnostics contain no private body content
      And no destination is created

  Rule: Rollback is best-effort per created path and retains the migration failure

    Scenario Outline: A disappeared destination does not interrupt rollback
      Given several destinations exclusively created by this invocation
      And one created destination disappears before rollback
      When a later migration <operation> fails
      Then rollback checks every other created destination and removes only matching inodes
      And the original migration failure is thrown unchanged when cleanup is complete
      And every legacy source remains byte-identical

      Examples:
        | operation |
        | open      |
        | write     |

    Scenario Outline: Remaining cleanup failures and replacements are explicit
      Given several destinations exclusively created by this invocation
      And one created path disappears and another is replaced by a different file or symlink inode
      And a remaining destination's rollback <operation> fails
      When a later migration open or write fails
      Then rollback continues through every created path
      And the replacement and its symlink target are never removed
      And successfully removable invocation-created files are removed
      And an aggregate failure retains the original migration error as its cause
      And diagnostics identify each retained path and cleanup failure without claiming complete rollback
      And every legacy source remains byte-identical

      Examples:
        | operation |
        | lstat     |
        | unlink    |

    Scenario Outline: A descriptor close failure cannot replace an earlier failure
      Given an exclusively created destination whose inode was recorded
      When its <operation> fails and closing that descriptor also fails
      Then every recorded destination is still considered for rollback
      And the first operation failure remains the aggregate cause and first error
      And the close failure is reported with the destination and uncertain descriptor state
      And the original source bytes remain unchanged

      Examples:
        | operation |
        | write     |
        | fsync     |

    Scenario: Exclusive creation followed by fstat failure reports unknown ownership
      Given open created a destination exclusively
      When fstat fails before its inode can be recorded
      Then the unverified destination is retained with an explicit ownership diagnostic
      And that diagnostic does not claim rollback completed
      And other verified invocation-created files are rolled back
      And an intervening replacement is never blindly deleted
      And the original fstat failure remains the aggregate cause

    These inode checks are not an OS sandbox or atomic protection against
    concurrent source or ancestor replacement.

  Rule: Scope controls definitions and optional scratch copying

    Scenario Outline: Migrate a project declaration without user promotion
      Given a legacy <legacy> declaration
      When a plan is approved for <scope>
      Then it copies only to <canonical>
      And it creates no user-scope agent.md

      Examples:
        | scope         | legacy                  | canonical                            |
        | project       | .pi/agents/reviewer.md   | .pi/agents/reviewer/agent.md          |
        | project-local | .pi/agents/reviewer.local.md | .pi/agents/reviewer.local/agent.md |

    Scenario: Copy an ordinary legacy workspace only when its project slug is selected
      Given ordinary workspaces/reviewer/one and workspaces/reviewer/two
      When only one is explicitly selected in workspaceProjects
      Then only one is copied under agents/reviewer/workspace/one
      And two remains untouched and excluded from the plan

    Scenario: Legacy Git workspaces require a manual decision
      Given a legacy workspace containing a .git file or directory
      When it is inventoried or selected
      Then the plan marks it blocked and manual
      And it is never copied, renamed, removed or presented as ordinary scratch

  Rule: Refuse ambiguous and unsafe plans before writing

    Scenario: Existing destinations or same-name sources conflict
      Given an existing canonical destination or two same-scope flat declarations of one name
      When migration is planned or applied
      Then it is refused without overwriting any file
      And originals stay byte-identical

    Scenario: Symlinks and traversal cannot escape either root
      Given symlinks in a source or target tree or an unsafe Agent or project slug
      When migration is planned or applied
      Then it is refused without reading through or writing through the link

    Scenario: A stale or tampered plan cannot authorize new bytes or paths
      Given an approved plan whose source changed or whose destination was altered
      When applyAgentMigration is called
      Then revalidation rejects it before any write
      And no legacy source or existing destination is modified
