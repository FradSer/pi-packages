Feature: Memory management with auto-memory guidance and manual consolidation
  The memory extension provides an auto-memory prompt guidance toggle and manual
  consolidation via the /memory menu and /consolidate command.
  When auto-memory is on, prompt guidance is injected telling the LLM to capture
  and organize durable decisions/preferences into memory on its own when needed.
  Consolidation is NEVER triggered automatically by context fill or agent settle;
  it only runs on manual user invocation in the background.

  Background:
    Given the pi-memory-fradser package is installed

  Scenario: Injects auto-memory guidance when auto-memory is on
    Given auto-memory setting is on
    When before_agent_start runs
    Then it injects auto-memory prompt guidance telling the LLM to actively capture durable facts
    And it does not include auto-consolidation threshold instructions

  Scenario: Omits auto-memory guidance when auto-memory is off
    Given auto-memory setting is off
    When before_agent_start runs
    Then it does not inject auto-memory prompt guidance
    And it still injects existing active project memories if any exist

  Scenario: /memory management menu includes auto-memory toggle
    Given the user opens the /memory menu
    Then it offers options to consolidate memory, edit user instructions, edit project instructions, open memory folder, and toggle auto-memory
    And selecting toggle auto-memory flips the setting and persists it

  Scenario: No automatic consolidation runs on context fill or agent settle
    Given the agent settles after any turn regardless of context usage
    Then no automatic consolidation run is started

  Scenario: Dedicated /consolidate command is a sibling of /memory
    Given the user types /consolidate
    Then the extension starts manual consolidation without opening the menu

  Scenario: Select the memory consolidation model from the management menu
    Given the model registry contains available models
    When the user chooses model selection from the /memory menu
    Then the menu offers the available models
    And selecting one persists its provider and model for future consolidation runs

  Scenario: Manual consolidation scopes consolidation to the current session's related memories
    Given the current session contains durable memory candidates
    When manual consolidation starts
    Then it first extracts those candidates from the current session context
    And it reads the indexes and only related existing memory files
    And it does not scan unrelated memory files for consolidation
    And it clusters, checks staleness, merges, prunes, and privacy-checks that related set
    And it synchronizes safe results to .memory

  Scenario: Manual consolidation runs in the background without exposing an implementation requirement
    Given memory consolidation is manually started
    Then it runs without blocking the active session
    And the user sees progress and completion status
    And the user-facing behavior does not require a particular background agent implementation

  Scenario: Manual consolidation starts with the selected model
    Given a memory consolidation model is configured
    When memory consolidation is manually started
    Then the background consolidation run uses that provider and model
    And no follow-up message blocks the current session

  Scenario: Background consolidation disables installed extensions
    Given memory consolidation is manually started
    When the child Pi process is launched in JSON print mode
    Then it includes --no-session and --no-extensions
    And installed recap extensions cannot run in the disposable child session

  Scenario: Shows a dreaming widget above the input editor while consolidating
    Given a consolidation run was just started
    Then ctx.ui.setWidget renders a "dreaming" indicator above the editor
    And the widget is cleared when the run exits

  Scenario: Only one dreaming consolidation runs at a time
    Given a consolidation run is still running
    When another consolidation is triggered
    Then no second consolidation run is started
    And the user is notified that consolidation is already running

  Scenario: Consolidation captures an immutable active-branch snapshot
    Given the current session has an active branch and a durable memory candidate
    When manual consolidation starts
    Then the parent writes a snapshot before spawning the child
    And the child reads the snapshot instead of a live session file
    And later turns, compaction, or branch changes do not alter the captured input

  Scenario: no-context explicitly disables session capture
    Given the user types /consolidate no-context
    When manual consolidation starts
    Then the run records that context capture is disabled
    And the child does not read a session file or live branch
    And the advertised snapshot digest matches the exact disabled snapshot bytes

  Scenario: Empty durable scope is a no-op
    Given the captured context contains no durable memory candidate
    When manual consolidation starts
    Then it does not scan or rewrite unrelated memory files
    And it reports a verified no-op result

  Scenario: Empty first-run scope initializes a verifiable no-op
    Given no harness memory root or public .memory root exists yet
    And the captured context contains no durable memory candidate
    When manual consolidation starts
    Then it creates only the required empty roots and indexes
    And it reports a verified no-op result without changing unrelated project files

  Scenario: Project scope key is distinct from the run scope digest
    Given the parent supplies a project scope key and a different run scope digest
    When the structured validator checks the consolidation plan
    Then it accepts both canonical identity fields
    And it rejects only an alias that disagrees with its own canonical field

  Scenario: Child output is a read-only structured plan
    Given a consolidation run is active
    When the child finishes
    Then its completion is accepted only when one bounded schema-valid plan matches the run id and scope digest
    And child prose, tool output, G1 through G8 text, and arbitrary PASSED text cannot prove success

  Scenario: Bounded JSONL parsing tolerates the final newline
    Given a child emits exactly the configured maximum number of JSONL records followed by a newline
    When the parent parses the child output
    Then the trailing empty line does not count against the record limit
    And a matching structured plan can still be accepted

  Scenario: Native consolidation parsing uses the shared output bounds
    Given a child emits output beyond the configured stdout, line, or plan bounds
    When the parent finishes parsing the child output
    Then it rejects the run even if a plan-like event was observed

  Scenario: Child plan extraction rejects malformed structured plan events
    Given a child emits a consolidation plan event whose plan is an array or scalar
    When the parent parses the child output
    Then it rejects the event instead of treating the wrapper as a plan

  Scenario: Parent supplies the authoritative selected scope to the child
    Given memory roots contain existing memory files when a consolidation run starts
    When the parent builds the child task prompt
    Then it embeds the exact parent-derived selected scope as JSON in the task header
    And the procedure requires the plan's selected array to be exactly that set of names with identical casing
    And the child is never asked to derive selected names from the snapshot

  Scenario: Failed consolidation runs keep bounded diagnostics
    Given a consolidation child exits without a verified consolidation
    When the parent finishes handling the failure
    Then it writes bounded stdout and stderr captures into the run directory
    And it retains the run directory artifacts while releasing the lock

  Scenario: Pre-mutation plan failures retry once with a fresh planner
    Given a consolidation child produced no schema-valid plan or its plan was rejected by validation
    And no memory mutation has been applied yet
    When the parent handles the failure on the first attempt
    Then it releases the failed run while keeping its diagnostics
    And it spawns exactly one replacement planner against the same run inputs
    And every attempt passes the same validation gates before any mutation
    And a failure after memory mutation is never retried

  Scenario: Pre-run mirror normalization repairs safe-file drift
    Given the harness and public copies of a safe memory file differ before the run
    When a consolidation run is created
    Then the parent overwrites the older copy with the newer side's bytes first
    And the repair direction is reported in the task header and notification
    And both indexes are regenerated so post-apply validation sees consistent mirrors

  Scenario: Privacy violations and orphans are removed before planning
    Given a private-marked memory file exists under public
    And a public file has no harness copy while the harness root exists
    When a consolidation run is created
    Then both files are removed from public before the snapshot is captured
    And a missing harness root imports public files instead of deleting them

  Scenario: Parent validates before and after scoped mutation
    Given the child returns a valid plan for selected memory files
    When consolidation applies the plan
    Then the parent validates the plan before mutation
    And it rechecks source hashes before applying changes
    And it validates the final harness and public state after the last mutation
    And it reports success only from the matching parent-owned receipt

  Scenario: Mirror application rolls back when a public write fails
    Given a selected safe memory rewrite has a valid harness and public predecessor
    When the public mirror write fails during the transaction
    Then the harness and public predecessor bytes remain unchanged
    And no private copy is exposed publicly
    And the run fails before a success receipt is written

  Scenario: A later operation failure rolls back earlier writes
    Given a transaction has already written one selected memory file
    When a later selected operation exceeds the bounded memory file size
    Then the earlier harness and public writes are restored byte-for-byte
    And no partial index is left behind

  Scenario: Receipt validation requires the declared post phase
    Given a receipt has valid identity and final hashes but no phase
    When the parent verifies the post-apply receipt
    Then validation fails before completion is reported

  Scenario: Receipt storage matches its declared phase
    Given the parent has a pre-apply consolidation receipt
    When it attempts to store that receipt as a post-apply receipt
    Then the write fails before the post-apply receipt path is created

  Scenario: Session shutdown cancels consolidation safely
    Given a consolidation child is still running
    When the session shuts down
    Then the child is terminated with close observed
    And the lock, run directory, and dreaming widget are cleaned up
    And a late child event cannot notify or mutate the replacement session

  Scenario: Shutdown invalidates completion after an asynchronous boundary
    Given consolidation completion is awaiting validation or apply
    When the session shuts down before that await resolves
    Then completion rechecks its generation and cancellation state
    And it does not recreate run material, mutate memory, write receipts, or notify success

  Scenario: Concurrent Pi processes use a shared project lock
    Given another Pi process owns a consolidation lock for this project
    When consolidation is triggered
    Then no second child is spawned
    And the user receives a lock diagnostic

  Scenario: A stale lock from a dead same-host process is reclaimed
    Given a consolidation lock exists for this project
    And its owner pid is dead on this host
    When consolidation is triggered again
    Then the dead-owner lock is removed and acquisition retries once
    And a lock owned by a live process still resolves as contention

  Scenario: First-run lock initialization races resolve as contention
    Given two Pi processes initialize the same missing agent memory directory concurrently
    When both attempt consolidation
    Then exactly one process acquires the lock
    And the other receives a lock-contention diagnostic instead of a setup failure

  Scenario: Consolidation run directories reject symlink escapes
    Given the configured agent memory runs directory is a symlink
    When a consolidation run is created
    Then the run fails closed without creating files outside the configured agent directory

  Scenario: Memory model selection uses one allowed-model policy
    Given scoped models are configured
    When a model is selected from the menu or entered manually
    Then both paths accept only the same allowed model set
    And an isolated-worker-incompatible provider is rejected before spawning

  Scenario: Instruction editing follows Pi's resolved context resource
    Given Pi resolves an AGENTS override or ancestor context file
    When the user edits project instructions in TUI or RPC mode
    Then the extension edits the same resource Pi injects

  Scenario: Loader and consolidation share one strict memory filename policy
    Given a memory root contains a valid Markdown basename, punctuation, and an upper-case extension
    When memory injection and consolidation inspect the root
    Then only the valid lower-case Markdown basename is accepted by both paths
    And rejected names cannot be injected and later fail privacy validation

  Scenario: Final receipt binds the exact plan artifact bytes
    Given a validated plan has been applied and a post receipt records its raw plan digest
    When the plan artifact is replaced with another schema-valid plan before final validation
    Then final validation rejects the receipt even when identity, selected scope, and final memory hashes still match
