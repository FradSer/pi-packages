Feature: User intent and current task handoff in Pi
  The package preserves original requests and gives the next session current evidence.

  Scenario: A user starts work
    Given the sdlc extension is loaded in a writable working directory
    When Pi starts a run from a user message
    Then INTENT.md uses the course title, Author and Status line, and five exact English sections
    And the original request is retained as quoted source text
    And HANDOFF.md links to INTENT.md and keeps one latest lifecycle checkpoint
    And the model must read both records before work and update the handoff before finishing or pausing
    And structured prompt sections from other extensions remain intact

  Scenario: A task receives a correction
    Given an existing intent and current handoff
    When another real user message arrives in the same session
    Then the correction is retained without discarding earlier source requests
    And custom extension messages are not recorded as user intent

  Scenario: Raw input and steering remain faithful
    Given an interactive or RPC user prompt before host template expansion
    When the input is expanded, queued as a follow-up or delivered as steering during work
    Then the original text is captured once in INTENT.md
    And generated extension user messages are not captured as user intent

  Scenario: Work settles or is interrupted
    Given a current handoff with decisions and verification evidence
    When Pi settles normally, aborts, reports an error, or shuts down during work
    Then only the latest lifecycle checkpoint is replaced
    And the model's current evidence and next steps remain
    And stopping does not establish task completion
    And prompts and final responses are not copied into the handoff
    And the whole handoff must stay below 200 lines without a per-turn journal
    And a model error followed by successful recovery does not leave a stale error status

  Scenario: A workspace has unsafe documents or conflicting writers
    Given symbolic links, hard links, special files, malformed markers or a held write lock
    When the extension records a request or checkpoint
    Then it reports a recording failure and preserves existing evidence
    And it does not follow external file targets or take over another writer's lock

  Scenario: A package is installed from an archive
    Given the unscoped pi-sdlc package manifest and its packed files
    When native Pi loads index.ts with unrelated resources disabled
    Then the extension loads its own workflow and Markdown templates
    And real read and write tool calls update the intent and handoff
    And RPC abort preserves the latest unfinished state

  Scenario: A change follows the complete playbook
    Given an intent, independent adapters and version-controlled artifacts
    When native Pi calls the sdlc tool from intent through maintain
    Then current checks, evaluations and approvals gate every transition
    And a healthy release reaches maintain and produces a task archive
    And a metric breach produces a new intent for triage
    And failed or stale evidence blocks progression
