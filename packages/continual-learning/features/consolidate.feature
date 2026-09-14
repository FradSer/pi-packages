Feature: Memory management with automatic learning and manual consolidation
  The memory extension learns from settled user tasks when auto-memory is on.
  The /memory menu and /consolidate command also start consolidation explicitly.
  Read-only planners propose changes; the parent validates and applies them.

  Background:
    Given the pi-memory-fradser package is installed

  Scenario: Injects auto-memory guidance when auto-memory is on
    Given auto-memory setting is on
    When before_agent_start runs
    Then it explains that a parent-owned learner captures durable facts after the task
    And it does not ask the main model to bypass validation by writing memory directly
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

  Scenario: Automatic consolidation follows a settled user task
    Given auto-memory is enabled and a user task has completed
    When the agent settles after all automatic continuations
    Then one automatic consolidation pipeline starts regardless of context usage
    And repeated settled events do not start duplicate pipelines

  Scenario: Dedicated /consolidate command is a sibling of /memory
    Given the user types /consolidate
    Then the extension starts manual consolidation without opening the menu

  Scenario: Select the memory consolidation model from the management menu
    Given the model registry contains available models
    When the user chooses model selection from the /memory menu
    Then the menu offers the available models
    And selecting one persists its provider and model for future consolidation runs

  Scenario: Memory resolves a complete private root and sanitized project mirror
    Given memory files exist in the Harness private root and project .memory root
    When active project memories are loaded
    Then the private copy wins for the same filename
    And non-conflicting entries from both roots remain active

  Scenario: Manual consolidation scopes consolidation to the current session's related memories
    Given the current session contains durable memory candidates
    When manual consolidation starts
    Then it first extracts those candidates from the current session context
    And it reads the indexes and only related existing memory files
    And it does not scan unrelated memory files for consolidation
    And it clusters, checks staleness, merges, prunes, and privacy-checks that related set
    And it synchronizes safe results to project .memory
    And it keeps private results only in the Harness private root

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

  Scenario: Background consolidation disables unrelated discovery
    Given memory consolidation is manually started
    When the child Pi process is launched in JSON print mode
    Then it uses the shared minimal Pi worker arguments
    And extension, skill, prompt-template, context-file, and theme discovery are disabled
    And only read, grep, find, and ls are available in the disposable child session

  Scenario: Shows a dreaming widget above the input editor while consolidating
    Given a consolidation run was just started
    Then ctx.ui.setWidget renders a "dreaming" indicator above the editor
    And the widget uses shared Pi-kit spinner cadence, theme style callbacks, and native-row geometry
    And consolidation status notifications use the shared Pi-kit notification helper
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
    Given no Harness private root or project .memory root exists yet
    And the captured context contains no durable memory candidate
    When manual consolidation starts
    Then it creates only the required empty roots and indexes
    And it reports a verified no-op result without changing unrelated project files

  Scenario: A non-project parent directory never becomes a project memory mirror
    Given the current directory is not a Git worktree root
    When memory paths are resolved
    Then its project .memory mirror is disabled
    And its readable Harness private root remains available
    And private-only consolidation can pass final validation without a project mirror

  Scenario: The Pi agent configuration directory never becomes project shared memory
    Given the current directory is the Pi agent configuration directory
    When memory paths are resolved
    Then its project .memory mirror is disabled

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

  Scenario: Context evidence can create bounded new memory beside the existing scope
    Given the current project has no existing memory files
    And the immutable snapshot contains a user preference
    When the read-only planner returns a newMemories proposal
    Then selected remains the empty parent-owned scope
    And the new memory name is validated in a separate bounded scope
    And the proposal is written transactionally to the private root
    And a safe proposal is mirrored byte-for-byte to project .memory

  Scenario: New memory evidence is tied to the immutable snapshot
    Given a newMemories proposal cites a snapshot entry index and exact quote
    When the parent validates the plan
    Then the cited entry must be a user or tool result
    And an assistant-only quote cannot create a durable memory
    And changing the snapshot after planning rejects the proposal

  Scenario: Untouched existing memory keeps its index-owned privacy classification
    Given the selected scope contains a private Harness-only memory
    And the planner mislabels that memory as safe but proposes no operation for it
    When the parent validates the unchanged final memory state
    Then the valid Harness index remains authoritative
    And the consolidation is not rejected for the planner's unused inventory label

  Scenario: New memory privacy defaults follow its semantic kind
    Given a context-derived preference and a verified project fact are proposed
    When the parent validates the plan
    Then the preference defaults to private
    And the verified project fact may be explicitly safe and mirrored
    And a preference cannot be classified safe without an explicit privacy-safe contract

  Scenario: Context-derived memory never persists secrets
    Given a new memory proposal or evidence quote contains a credential or token
    When the parent validates the plan
    Then the proposal is rejected before any root is mutated

  Scenario: New memory writes roll back with existing memory writes
    Given a transaction contains an existing rewrite and a new memory proposal
    When a later write or index update fails
    Then both roots and their indexes return byte-for-byte to their predecessor state

  Scenario: A frozen session context survives later consolidation phases
    Given the parent snapshots the session manager before memory planning
    When the original branch and context entries are mutated
    Then reads through the snapshot session context return the original bounded values
    And other session manager methods remain callable with their original receiver

  Scenario: Failed consolidation runs keep bounded diagnostics
    Given a consolidation child exits without a verified consolidation
    When the parent finishes handling the failure
    Then it writes bounded stdout and stderr captures plus a compact activity summary into the run directory
    And it retains the run directory artifacts while releasing the lock

  Scenario: Identical duplicate plan records collapse before validation
    Given a child plan repeats one per-item record byte-for-byte
    When the parent extracts the plan
    Then identical duplicates collapse to their first occurrence and the run proceeds
    But conflicting duplicates stay intact so validation rejects the ambiguity

  Scenario: Pre-mutation plan failures recover silently and continue the live pipeline
    Given a consolidation child produced no schema-valid plan or its plan was rejected by validation
    And no memory mutation has been applied yet
    And the failure was not caused by a planner model execution error
    When the parent handles the failure on the first attempt
    Then it releases the failed run while keeping its diagnostics
    And it spawns exactly one replacement planner against the same run inputs without reporting the recoverable rejection to the user
    And the live pipeline waits for the replacement attempt before deciding whether to run Harness and AGENTS.md consolidation
    And every attempt passes the same validation gates before any mutation
    And a failure after memory mutation is never retried

  Scenario: Planner model execution failures are labeled as model errors
    Given a consolidation child exits with every planner model call ending in stopReason error
    And the child produced no stderr output and no structured consolidation plan
    When the parent classifies the plan phase failure
    Then on both zero and non-zero exit codes it labels the failure as a planner model error carrying the captured provider error, truncated from the head only for the notification budget
    And validator rejection reasons are emitted once per category without duplicated prefixes
    And it does not spend the fresh-planner retry because the replacement inherits the same failing model
    But a plan-phase failure with child stderr output stays classified as missing-plan and keeps the retry
    And a successful model retry attempt clears the earlier execution error so a later structured plan still passes

  Scenario: Dreaming status is flush-left
    Given the consolidation pipeline is active in the TUI
    When the Dreaming status row is rendered
    Then the spinner starts in the first column without a leading space

  Scenario: Dreaming timeout is labeled as the budget it exceeded
    Given the consolidation child outlives the dreaming budget and is terminated by the parent timer
    When the parent reports the non-zero completion
    Then it names the exceeded dreaming budget instead of a raw exit code like 143
    And the timeout is not classified as a planner model error

  Scenario: Fresh planner retry receives the rejection feedback
    Given the first attempt failed with a validator rejection or a missing-plan classification
    And no memory mutation has been applied yet
    When the parent spawns the fresh planner re-running the same immutable-input capture pipeline
    Then the task header additionally carries the previous rejection reason and instructs the planner to resolve every cited issue
    And only that feedback line may differ in the task text; validation gates and receipt requirements stay identical across attempts
    And each attempt captures its own fresh snapshot under its own run identity

  Scenario: Grounding observations cite files not directories
    Given the consolidation procedure instructs repository grounding
    When the planner cites a found or updated observation
    Then the cited path must resolve to an existing file under the repository root
    And the procedure states skill directories must be cited through a concrete file such as the skill's SKILL.md

  Scenario: Readable private root normalizes path whitespace
    Given the canonical project path contains a directory named Home Lab
    When memory paths are resolved
    Then the private root uses Home-Lab with no whitespace

  Scenario: Legacy private memory migrates into the agent-owned private root
    Given a project has private memory under an old SHA-256 agent directory or an older readable directory containing whitespace
    And the readable destination already contains harness-only index markers
    When memories are loaded or a consolidation run starts
    Then legacy files merge into the escaped-project-path private root without overwriting existing files
    And private index markers from both roots survive the migration even when the same filename conflicts
    And a migrated legacy source is removed only when every entry is a recognized regular memory file or index
    But a source containing any unsupported entry remains intact so migration cannot discard unrecognized data
    And private memory belongs only below the Pi agent directory

  Scenario: Project-local private memory storage is absent
    Given the package supports an agent-owned private root and a project-shared mirror
    When its runtime, tests, and documentation are inspected
    Then no project-local private memory directory is recognized, migrated, guarded, or documented

  Scenario: Pre-run mirror normalization repairs safe-file drift
    Given the private and project-shared copies of a safe memory file differ before the run
    When a consolidation run is created
    Then the parent overwrites the older copy with the newer side's bytes first
    And private-marked or orphan project-shared files are removed
    And both indexes are regenerated before planning

  Scenario: Parent validates before and after scoped mutation
    Given the child returns a valid plan for selected memory files
    When consolidation applies the plan
    Then the parent validates the plan before mutation
    And it rechecks both root source hashes before applying changes
    And it validates the final privacy split and mirror state after the last mutation
    And it reports success only from the matching parent-owned receipt

  Scenario: A later operation failure rolls back earlier writes
    Given a transaction has already written one safe memory file to both roots
    When a later selected operation exceeds the bounded memory file size
    Then both earlier root writes are restored byte-for-byte
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
