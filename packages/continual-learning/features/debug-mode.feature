Feature: Continual-learning debug records
  Debug records describe actual plugin activity in private local storage.
  They are untrusted diagnostic evidence, never Memory or mutation authority.

  Scenario: Debug logging defaults on and can be disabled without enabling learning
    Given continual-learning is loaded without a debug setting
    When its event handlers, commands and tools run
    Then each invocation records its source, project, session, input context and terminal outcome
    And automatic learning remains under its existing settings
    When debug is false in continual-learning.json
    Then subsequent invocations create no debug records
    And changing debug preserves other configuration fields

  Scenario: Relate nested activity to the invocation that caused it
    Given two plugin invocations overlap in different sessions
    When they emit notifications, tool transitions and learning receipts
    Then every record retains its own invocation and session binding
    And receipts retain their batch identity, outcomes, diagnostics and artifact references
    And a large context cannot consume the separate result projection budget
    And a completed callback is not reported as successful learning

  Scenario: Errors and cancellations preserve plugin behavior
    Given a plugin callback fails, blocks a tool or is cancelled
    When debug observes the callback
    Then it records the actual error or outcome with a bounded stack and context
    And it preserves synchronous returns, asynchronous results and thrown error identity
    And a debug storage failure does not change the plugin result or execution decision
    And a fixed diagnostic reports unavailable logging without exposing private error text

  Scenario: Debug context never stores credentials or binary payloads
    Given inputs, results or errors contain credential-shaped material
    When debug serializes them
    Then sensitive values are replaced with hash-only markers before truncation
    And authentication headers, environment values and image bytes are never copied
    And ordinary safe context remains readable
    And omitted context is explicitly marked
    And no debug content enters Memory, shared project files or model prompts

  Scenario: Private append records refuse redirected or non-regular targets
    Given debug uses the canonical project scope under the private agent directory
    When a directory or log target is replaced by a symlink or FIFO
    Then logging refuses the target without blocking or changing an unrelated file
    And new directories have mode 0700 and new log files have mode 0600
    And concurrent processes use separate exclusive log files
    And log segments rotate without deleting earlier evidence

  Scenario: Disabling debug stops an already running invocation from recording later data
    Given an invocation and a pending lifecycle batch are waiting with debug enabled
    When the user turns debug off before that invocation continues
    Then its later messages, callback result and pending lifecycle batch are not recorded
    And a final configuration record explains the logging boundary
    And a genuinely older unclosed invocation remains reported as unclosed
    And the inspector never infers a clean closure from a later shutdown timestamp

  Scenario: Usage counts cannot disguise credential collections
    Given access_tokens and refresh_tokens contain credentials
    When debug projects the record alongside numeric token usage
    Then the credential collections are redacted
    And only explicitly named numeric usage fields remain readable

  Scenario: Observing returned objects and asynchronous results preserves behavior
    Given a callback returns an object with throwing property getters or a foreign Promise
    When debug observes it with logging enabled or disabled
    Then it never invokes result property getters
    And a rejected foreign Promise or thenable is recorded as failed when logging remains enabled
    And the original result or rejection reaches the caller

  Scenario: Sensitive project paths retain private scope identity
    Given a canonical project path itself matches the sensitive-material detector
    When debug records an invocation
    Then it selects the log directory using the original canonical path
    And it retains a project digest beside the redacted display path
    And the inspector can identify that project without exposing the path

  Scenario: Inspect overlapping writers and configured agent path aliases
    Given two writers started in one order and recorded events in a different order
    When the inspector reads them using an alias of the configured agent root
    Then it selects recent records by actual event timestamps
    And the configured root alias resolves to the same private directory
    And symlinks below that root remain refused

  Scenario: Inspect and configure debug from the existing learning command
    Given the plugin has registered the learning command
    When the user invokes learning debug or learning debug on or learning debug off
    Then the command reports the effective setting and exact private log directory
    And no model call, learning pipeline or additional command registration is required
    And unrelated learning requests still reach their original handler

  Scenario: Bounded context references reduce repeated tool-schema logging
    Given one root invocation has a context containing complete tool definitions
    When its nested tool transitions, notifications and result records are appended
    Then one private context snapshot retains the sanitized context for that invocation
    And nested records reference its digest without copying the complete definitions
    And authentication fields remain redacted in the snapshot
    And the inspector joins the snapshot or reports unavailable context explicitly
    And total log size stays far below repeated copies of the same context

  Scenario: Repeated lifecycle handlers remain separately attributable
    Given six plugin handlers observe one session_start event
    When debug records their outcomes
    Then it retains six handler invocation identities and terminal outcomes
    And it does not duplicate the complete session context for each successful handler
    And any handler failure retains its own failed record and stack
    And the inspector reports missing handlers without treating call counts as sessions
    And the batch handler count counts identities, not started and terminal rows

  Scenario: Zero-write and applied pipelines have explicit closed dispositions
    Given one screened pipeline writes no changes and another applies validated Memory
    When debug records each pipeline:closed
    Then their outcomes name screened and applied respectively
    And unverified is reserved for a genuinely unknown terminal state
    And the recorded batch identities match their receipts

  Scenario: Missing shutdown events and sampling remain explicit evidence
    Given a process exits without a Pi session_shutdown event
    When a separate process-exit record is retained
    Then the inspector distinguishes missing shutdown from unclosed callbacks
    And a possible abnormal exit is reported as evidence only, not a confirmed crash
    When a project has more log segments than the inspector samples
    Then it reports total files, sampled files, byte coverage and incomplete coverage
    And earlier segments remain on disk without automatic deletion

  Scenario: Detached background learning retains its invocation and batch identity
    Given an agent_settled callback launches a detached completion with debug enabled
    When the detached task later writes a receipt and closes its pipeline
    Then its records share one batch identity and the original invocation binding
    And disabling debug while it runs stops later records without changing learning

  Scenario: Internal stages expose controlled categories and artifact identities
    Given a learning run prepares a source collector, a Jev judgment and a mutation history
    When parent-owned observability records are written
    Then they carry only their available batch, run, ledger or change identities
    And worker terminal categories, usage completeness and controlled stop reasons remain separate evidence
    And no complete worker wire, provider headers, Memory bodies or credentials are copied
    And missing identities stay missing rather than being inferred from times or token totals

  Scenario: Local real-model verification uses a zero-call preflight and disposable agent root
    Given the user asks to exercise the installed config with a real model
    When the runner checks pending backlog, triggers and expected transport before a call
    Then it requires a disposable agent root and explicit budget admission
    And an offline loopback path remains available for plugin wiring verification
    And controlled wiring evidence is reported separately from learning benefit

  Scenario: Repository-only reflection and repair uses retained evidence
    Given the continual-learning debug skill belongs to this repository
    When its read-only inspector receives an isolated agent root and project path
    Then it selects only matching project records and reports failures, unfinished invocations and context omissions
    And it refuses symlinks, non-regular files and malformed records as incomplete evidence
    And the skill requires a failing regression, a minimal repair and affected checks
    And it preserves original logs, learning gates and unrelated work
