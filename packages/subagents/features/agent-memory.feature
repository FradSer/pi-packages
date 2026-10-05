Feature: Every disk identity owns a private capability Memory

  Agent Memory records reusable methods, judgment criteria and operating patterns,
  not project facts, decisions or history. A valid disk agent.md declares identity;
  derived data directories do not. See VISION.md and AUTHORITY.md for authority.

  Rule: Memory lives inside the identity's private data home

    Scenario: A disk identity resolves one cross-project memory root
      Given a disk Agent named "reviewer" in any definition scope
      When its memory root is resolved
      Then the root is <agent-dir>/agents/reviewer/memory
      And no project working directory appears in the path
      And path resolution creates no directories

    Scenario: Discovery includes canonical durable homes, not temporary residue
      Given a user home containing a valid canonical agent.md
      And a project identity's private data home with valid package-owned state but no user agent.md
      And its lastProject still contains a valid matching canonical project definition
      And empty, malformed, legacy, unbound-state and temporary directories
      When memory roots are listed
      Then only existing memory folders in canonical durable homes are returned
      And they are returned in stable order without creating directories
      And valid state supplies the project location for declaration validation, never an identity
      And an unbound or removed project source is not discovered

    Scenario: A name or symlink cannot escape the memory root
      Given an invalid Agent name or an entry or proposal symlink leaving the memory root
      Including a dangling symlink to a not-yet-created outside file
      When a path is resolved or a write is attempted
      Then the operation is refused without writing outside the memory root
      But a configured agent directory reached through a symlink remains usable
      And the first append can create its missing memory subdirectory

  Rule: Both injected and saved indexes obey the UTF-8 byte budget

    Scenario: The block lists relevance cues, never entry bodies
      Given a memory folder holding capability entries with multi-paragraph bodies
      When the system-prompt block is built
      Then filenames and one-line descriptions are listed
      And entry bodies are not injected
      And the root is declared once
      And content is marked as untrusted reference data
      And relevance cues are single-line text without terminal escapes or control strings

    Scenario: Descriptions and omission notices share the budget
      Given long multibyte descriptions and more entries than fit
      When an injected block or MEMORY.md is built
      Then the complete text including child section heading, headers, notices and write guidance is at most 8 KiB
      And shortened descriptions carry a visible marker
      And omissions are counted against the total
      And entry files remain authoritative when the index is incomplete

    Scenario: A caller supplies a smaller budget
      Given a nonnegative byte budget smaller than the standard limit
      When an index or system-prompt block is built
      Then the complete text never exceeds that byte budget
      And a budget too small for useful guidance yields no partial guidance

    Scenario: No entries means no injected block
      Given an Agent whose memory folder is absent or empty
      When its block is built
      Then the block text is empty
      And discovery and injection do not provision data

  Rule: Appending follows the effective write grant

    Scenario: A read-only Agent cannot append
      Given an Agent whose grant has no edit, write, bash or powershell
      When it attempts to append an entry
      Then the append is refused naming the read-only grant
      And the block tells it to report the lesson in its result instead

    Scenario: A write-capable Agent appends and derived data follows
      Given a durable Agent granted write with existing package-owned state
      When it appends an entry with a name, description and body
      Then the entry is written inside memory/
      And the bounded MEMORY.md is regenerated
      And memoryEntryCount reflects the capability entries, not proposals
      And creation time, last project and unrelated state fields are preserved
      And the next accepted input's block includes the new entry

    Scenario: Shared state updates are serialized across parent and child
      Given two processes updating different package-owned state fields
      When the existing-state updater takes state.json.lock and publishes atomically
      Then each update reads the latest complete state under the same lock
      And neither update loses the other field or unknown data
      And missing state is not invented
      And malformed state, symlink paths and an occupied lock are refused
      And only temporary files and locks created by that operation are removed

    Scenario: Provisioning and index regeneration use the shared state contract
      Given a durable home with unrelated state fields and authoritative capability entries
      When storage provisions another project and MEMORY.md is regenerated
      Then state retains unrelated fields and creation time
      And lastProject and memoryEntryCount both reflect their latest updates

    Scenario: A shell grant is not read-only
      Given an Agent granted bash or powershell
      When write capability is decided
      Then the Agent is write-capable because a shell can write

    Scenario: Invalid entries do not overwrite the derived index
      Given a traversal name, reserved index name, oversized body or empty description
      When the entry is appended
      Then the append is refused without writing an entry

  Rule: Proposals remain unaccepted evidence

    Scenario: A proposal is recorded for review, not merged
      Given an Agent that learned a reusable method
      When it records a proposal with capability, applicability and limits
      Then a proposed file is written under memory/proposals/
      And no capability entry is created or included in the index
      And review and merge remain separate decisions owned by continual-learning

    Scenario: A read-only execution role may write a controlled proposal
      Given an Agent whose execution tool grant is read-only
      When it records a proposal through agent_memory
      Then a local candidate file is written as a controlled proposal exception
      And the candidate is unaccepted and never merged by this tool
      And direct capability append remains refused
      And read-only execution is not described as read-only disk access

  Rule: The child tool describes and returns its actual local write effects

    Scenario: Append creates or replaces the same-name capability entry
      Given a disk child with an effective write grant
      When append is called twice with the same entry name and different bodies
      Then the second body replaces the first under the same filename
      And only one capability entry is indexed
      And the description, snippet, action help and receipt disclose creation or replacement
      And no new overwrite action or authorization policy is introduced

    Scenario: Propose preserves optional metadata compatibility without merging
      Given a disk child with a read-only execution grant
      When propose supplies only body or optional title, name, description, applicability, limits and evidence
      Then the tool writes a candidate with the existing title and applicability fallbacks
      And the description, snippet, field help and receipt disclose an unaccepted local candidate
      And the tool never creates a capability entry or merges a proposal

    Scenario: Results expose schema-matching success and refusal data
      Given the child Memory tool and its flat parameter schema
      When append or propose succeeds or returns a refusal
      Then outputSchema validates structuredContent with action and outcome
      And successful receipts identify the file and its write effect
      And refusals identify a machine-readable code and diagnostic
      And existing details retain their outcome and error fields for UI callers
      And annotations say local writes may overwrite and are not read-only or idempotent

    Scenario: Invalid action fields are refused before local effects
      Given a bound disk child
      When a call has a wrong action, unknown or misplaced field, wrong field type or empty mandatory argument
      Then append requires nonempty string name, description and body
      And propose requires nonempty string body with optional string metadata
      And no Memory entry, index or proposal file is written
      And diagnostics do not stringify an invalid body into a capability

    Scenario: Authored body bytes reach the existing library unchanged
      Given an append or proposal body with leading and trailing spaces and CRLF
      When the tool validates the body as nonempty
      Then it passes the original body bytes to the Memory library
      And the library's existing persistence normalization remains unchanged

    Scenario: An already-aborted child write has no effect
      Given a bound disk child and an already-aborted signal
      When append or propose is executed
      Then a typed aborted refusal is returned before any local write
      And no promise is made about transactional cancellation after a write begins

    Scenario: Failure diagnostics are bounded reference text
      Given an invalid field or library failure with terminal controls and a long diagnostic
      When the child tool returns a refusal
      Then content, details and structuredContent share a sanitized bounded diagnostic
      And shortening carries the existing diagnostic truncation marker
      And the original input and library error remain unchanged

  Rule: The child contribution follows disk identity, not a Memory opt-in

    Scenario Outline: Every disk scope has Memory without a frontmatter switch
      Given a valid <scope> definition at its canonical agent.md path
      And no memory field in its frontmatter
      When it is discovered and its child contribution loads
      Then Agent Memory is available without an opt-in environment variable
      And append still follows the effective write grant
      Examples:
        | scope         |
        | user          |
        | project       |
        | project-local |

    Scenario: A durable child reloads the index for each accepted input
      Given a child contribution loaded for a disk identity
      When a capability entry is added between two inputs
      Then the next before_agent_start reads the current bounded index
      And it does not reuse a stale factory-time block

    Scenario: Temporary execution contributes no Memory
      Given a session-only role or an ambient extension without the internal child role marker
      When its child contribution would load
      Then no Memory tool or prompt handler is registered
      And no durable memory directory is created
      And temporary context cannot be promoted or recovered by defining the name later

    Scenario: An arbitrary role marker is not a disk binding
      Given an internal role name and existing memory or valid data state
      But no explicit canonical disk definition path and scope
      When an ambient child extension loads
      Then no Memory tool or prompt handler is registered
      And data existence is not treated as a user identity

    Scenario: A project child binds the explicit project definition
      Given a canonical project or project-local agent.md and original project path
      And an explicit definition path and scope in the child environment
      But no user agent.md in its private data home
      When its child contribution loads
      Then it validates that project declaration and registers Memory
      And a mismatched name, scope, noncanonical path or symlink is refused

    Scenario: A hard-linked canonical definition cannot bind Memory
      Given a valid canonical agent.md with an outside hard link to the same inode
      And an explicit definition path and scope in the child environment
      When its child contribution loads
      Then no Memory tool or prompt handler is registered
      And discovery does not list the hard-linked identity
