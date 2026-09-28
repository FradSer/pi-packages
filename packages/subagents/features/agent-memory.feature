Feature: Agent Memory is a persisted Agent's own capability record

  Agent Memory holds how an Agent works, never what some project says. It has
  exactly one home at user scope, it is opt-in per definition, and a Temporary
  Agent never gets one. Injection follows ADR-0003: a bounded index of filenames
  and one-line descriptions, never entry bodies.

  Rule: The folder is the Agent's own and only at user scope

    Scenario: The memory root resolves under the agent directory
      Given a persisted Agent named "reviewer"
      When its memory root is resolved
      Then the root is the agent directory joined with agents/reviewer
      And no project working directory appears in the path

    Scenario: An Agent name cannot escape the agents directory
      Given an Agent name containing path traversal
      When its memory root is resolved
      Then the call is refused rather than resolving outside the agents directory

    Scenario: Existing memory roots are discoverable for a consolidation bridge
      Given two Agents with memory folders and one without
      When the memory roots are listed
      Then exactly the two existing folders are returned in a stable order

  Rule: Injection carries an index, never bodies

    Scenario: The block lists entries without their content
      Given a memory folder holding two entries with multi-paragraph bodies
      When the system-prompt block is built
      Then each entry appears once with its filename and description
      And no entry body text appears in the block
      And the root is declared once rather than repeated per entry
      And the content is marked as untrusted reference data

    Scenario: A description too long for its share is shortened visibly
      Given one entry whose description far exceeds the per-entry budget
      When the block is built
      Then the shortened description carries the shortening marker
      And the entry is still listed

    Scenario: Entries beyond the budget are counted, not silently dropped
      Given more entries than the index budget can list
      When the block is built
      Then the omitted count is reported against the total
      And the block says the index may be stale and entry files are authoritative

    Scenario: An Agent with no memory folder gets no block at all
      Given an Agent whose memory folder does not exist
      When the block is built
      Then the block text is empty
      And the absence of a block is how "no Agent Memory" is expressed

  Rule: Writing is gated by the tool grant

    Scenario: A read-only Agent cannot append
      Given an Agent whose grant has no edit, write, bash, or powershell
      When it attempts to append an entry
      Then the append is refused naming the read-only grant
      And the block tells it to report the lesson in its result instead

    Scenario: A write-capable Agent appends and the index follows
      Given an Agent granted write
      When it appends an entry with a name, description, and body
      Then the entry file exists inside the memory root
      And MEMORY.md is regenerated from the entries present
      And a later session's index lists the new entry without reloading anything

    Scenario: A bash grant counts as write-capable
      Given an Agent granted only read and bash
      When write capability is decided
      Then the Agent is write-capable, because a shell can write

    Scenario: An entry name cannot escape the memory root
      Given an entry name containing path traversal
      When the entry is appended
      Then the call is refused rather than writing outside the root

    Scenario: An oversized entry is refused rather than truncated
      Given a body larger than the entry cap
      When the entry is appended
      Then the append is refused naming the cap

    Scenario: An entry without a description is refused
      Given an append with an empty description
      When the entry is appended
      Then it is refused, because the description is what the index carries

  Rule: A generalizing lesson is proposed, not merged

    Scenario: A proposal is recorded for review
      Given an Agent that learned a reusable method
      When it records a proposal with capability, applicability, and limits
      Then a proposal file is written under proposals/
      And the proposal is not an entry and does not appear in the index

    Scenario: A read-only Agent may still propose
      Given an Agent whose grant is read-only
      When it records a proposal
      Then the proposal is accepted, because proposing is reporting, not writing memory

  Rule: A Temporary Agent owns no Agent Memory

    Scenario: A session-scoped definition never gets memory
      Given an inline definition that asks for memory
      When it is registered as a session Agent
      Then its resolved memory flag is false
      And promotion, not the request, is what would create a folder

    Scenario: A persisted definition opts in explicitly
      Given a definition file carrying memory: true
      When it is discovered
      Then the resolved memory flag is true
      And a definition without the field resolves to false
