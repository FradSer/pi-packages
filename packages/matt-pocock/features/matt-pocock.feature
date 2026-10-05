Feature: Matt Pocock workflow harness
  Expose Matt Pocock engineering workflows through one Pi harness command
  without globally discoverable child skills.

  Scenario: Adversarial gateway requests preserve the current work item
    Given a Pi v1 session has an active workflow or standalone disclosure chain
    When malformed, incompatible, repeated, or unauthorized requests are attempted
    Then rejected requests do not partially change persisted state or active tools
    And valid aliases and repeated operations follow the catalog contract

  Scenario: Reading a reference does not invoke its user-only capability
    Given setup-matt-pocock-skills is a user-only standalone capability
    When the model gateway reads its disclosed domain reference
    Then only the reference body is returned without invoking the capability or changing workflow state
    And a direct model request to invoke the capability remains rejected

  Scenario: Delayed menus cannot mutate a replacement workflow
    Given a menu is waiting on a workflow choice for work item A
    When A is completed or cancelled and work item B starts before the old choice arrives
    Then the old menu is dismissed and cannot complete, transition, or overwrite B

  Scenario: A resolved menu choice cannot race a replacement workflow
    Given a menu choice has resolved for work item A
    When A is replaced before the asynchronous menu handler resumes
    Then validation and the selected action run together against A
    And the old choice cannot act on work item B

  Scenario: A decision cannot outlive its workflow state
    Given a decision is waiting for user input
    When the workflow ends, changes phase, or the session changes branch
    Then a late answer remains pending and cannot answer for the new state
    And the waiting selector and any native subprocess are cleaned up

  Scenario: Constructed resource and restore boundaries fail atomically
    Given a resource bundle or persisted record is at a catalog or size boundary
    When it is invalid or exceeds the UTF-8 byte limit
    Then it fails explicitly without partial delivery or state changes
    And a valid boundary case remains usable

  Scenario: The harness opens one workflow-routing menu
    Given a Pi session has loaded pi-matt-pocock
    When the user invokes /matt-pocock without arguments
    Then the harness presents the available workflow routes
    And it does not register one command per workflow

  Scenario: Selecting a route injects its procedure
    Given the user selects the hard-bug diagnosis route
    When the harness activates the route
    Then it persists diagnosing-bugs as the current procedure at the feedback-loop phase
    And it injects the diagnosing-bugs procedure into the session

  Scenario: A route or capability start carries the user's task
    Given the user invokes /matt-pocock with a catalog route or standalone capability followed by a task
    When the harness starts it
    Then the delivered procedure prompt carries that task as the user's target/request
    And the row shows that task instead of the phase or capability name
    And persisted workflow state keeps route, phase, and work-item identity only

  Scenario: Active workflow state survives a session restart
    Given the harness persisted a workflow route and phase in a custom session entry
    When the session starts again on that branch
    Then the harness restores the latest workflow state and procedure guidance
    And it does not add a duplicate visible workflow lifecycle event
    And it does not add an input-footer status

  Scenario: A prompt routes to and begins the relevant workflow
    Given no Matt Pocock workflow is active
    When the user invokes /matt-pocock with an arbitrary engineering prompt
    Then the harness forwards the prompt for autonomous workflow routing and execution
    And it does not reject the prompt as an unknown route

  Scenario: A partial match is forwarded instead of starting a workflow
    Given the user invokes /matt-pocock with a first word matching no route, capability, or management action
    When the harness routes the request
    Then it forwards the whole input for autonomous routing
    And it does not start a workflow from a partial match

  Scenario: A prompt cancels active workflow before rerouting
    Given a Matt Pocock workflow is active
    When the user invokes /matt-pocock with a new arbitrary engineering prompt
    Then the harness records that the current workflow was cancelled as superseded
    And it forwards the prompt for autonomous workflow or capability routing

  Scenario: A user explicitly selects a legal next procedure
    Given an idea-to-ship workflow is active at the shaping phase
    When the user selects a catalog-defined next procedure from the harness transition menu
    Then the harness persists the selected procedure and its catalog phase
    And it injects that procedure and its required dependency closure

  Scenario: An agent automatically transitions after completing a procedure
    Given an active idea-to-ship workflow has completed its shaping procedure
    When the next applicable procedure is clear from the workflow route
    Then the agent calls matt_pocock_active with that allowed target without waiting for user confirmation
    And the harness persists and returns the new procedure and phase

  Scenario: Active work receives concise phase guidance
    Given a workflow is active
    When an agent turn starts
    Then the harness adds compact workflow and phase guidance
    And it does not inject every procedure into the system prompt

  Scenario: Inactive sessions receive workflow routing guidance
    Given no workflow is active in the session
    When an agent turn starts
    Then the harness adds guidance on available engineering workflows and how to activate them
    And the guidance leads with starting a workflow via matt_pocock_workflow while naming no unavailable tool

  Scenario: Agent-document work uses a standalone capability without workflow state
    Given no workflow is active in the session
    When the user asks to create or edit a skill or agent instruction document
    Then the agent calls matt_pocock_workflow in capability mode for writing-for-agents
    And it does not create persistent engineering workflow state

  Scenario: A de-slop capability removes AI slop without workflow state
    Given no workflow is active in the session
    When the user asks to remove AI slop from the recent changes
    Then the agent calls matt_pocock_workflow in capability mode for deslop
    And it does not create persistent engineering workflow state
    And it rewrites fabricated evidence, evidence widening, defensive clutter, mock patching, and vacuous names while behavior, public interfaces, and test outcomes stay identical

  Scenario: The standards baseline rejects AI slop patterns in code review
    Given the code-review procedure builds its fixed standards baseline
    When the standards axis evaluates the diff
    Then the baseline includes cross-language AI slop patterns for fabricated evidence, evidence widening, defensive clutter, mock patching, and vacuous names
    And each pattern is a labelled judgement call overridden by a documented repository standard
    And the baseline skips any pattern that repository tooling already enforces

  Scenario: Agent autonomously starts a workflow through the baseline gateway
    Given a task matching a structured engineering workflow
    When the agent calls matt_pocock_workflow in workflow mode
    Then the harness activates the catalog entry for the requested route
    And the tool returns the entry procedure and required dependency closure
    And the session records the workflow state

  Scenario: Known procedure aliases normalize through the catalog
    Given the catalog records tight-red-loop and clarify-goal as known aliases
    When a consumer resolves either alias
    Then tight-red-loop resolves to diagnosing-bugs
    And clarify-goal resolves to wayfinder
    And workflow phase selection still comes from the catalog placement

  Scenario: The catalog is the single source of procedure truth
    Given the package bundles workflow, utility, reference, and asset resources
    When the procedure catalog is validated
    Then every bundled procedure resource is classified exactly once
    And every declared file, dependency, disclosure, alias, and transition resolves
    And every workflow route has exactly one entry with its title, menu label, and routing description
    And every internal reference has an inbound catalog edge
    And all workflow procedures in a route are reachable from the route entry

  Scenario: Exploration procedures allow bidirectional lateral transitions
    Given an active idea-to-ship workflow is at the research or prototype procedure
    When the agent needs to alternate between research and prototyping
    Then the catalog permits lateral transitions between research and prototype
    And it does not require backtracking to shaping

  Scenario: Bug diagnostics allow returning to root cause analysis
    Given an active hard-bug workflow is at the implementation or review phase
    When a hypothesis is disproven or requires renewed diagnosis
    Then the catalog permits transitioning back to diagnosing-bugs

  Scenario: Starting a workflow loads its mandatory dependency closure
    Given improve-codebase-architecture requires the shared codebase-design vocabulary
    When the architecture workflow starts
    Then the tool result contains both procedure bodies with stable source identifiers
    And it lists optional references without loading every disclosed resource
    And the injected bundle remains within the configured size limit

  Scenario: A workflow advertises only legal next transitions
    Given an architecture workflow is active at improve-codebase-architecture
    When the workflow tool returns its state contract
    Then it lists only the catalog-defined next procedures and terminal actions
    And a transition outside that set fails with the allowed alternatives
    And it does not restart the route default

  Scenario: The agent explicitly completes or cancels a workflow
    Given a workflow is active
    When the agent completes or cancels it through the workflow tool
    Then the terminal status is persisted with its work item identity
    And active-only workflow tools are disabled
    And later turns receive inactive workflow guidance

  Scenario: Standalone capabilities are reachable without child skills
    Given the package bundles one-shot productivity and engineering capabilities
    When the user opens the Matt Pocock menu or the model selects a curated capability
    Then writing-for-agents and the other catalog utilities are available through the single gateway
    And running one does not create persistent workflow state
    And the package still contains no SKILL.md file

  Scenario: Promoted upstream capabilities use the single Pi gateway
    Given the upstream catalog includes the promoted pr and retro capabilities
    When the user selects either capability through /matt-pocock
    Then the gateway injects its adapted plain Markdown procedure
    And it does not create a persistent workflow state for the capability

  Scenario: Domain modeling follows the upstream GLOSSARY rename
    Given the domain-modeling procedure is loaded
    When it describes the project's domain document
    Then it refers to GLOSSARY.md and GLOSSARY-MAP.md
    And it does not require the removed CONTEXT-FORMAT resource

  Scenario: Conditional references load through the active gateway
    Given an active procedure or one of its required dependencies discloses a reference by catalog id
    When the agent loads that reference
    Then the gateway returns the referenced body with a stable source identifier
    And internal Markdown pointers use stable catalog source ids instead of unresolved relative paths
    And references outside the active procedure disclosure set are rejected

  Scenario: Procedure texts route agents through the catalog gateway, not Pi skills
    Given one procedure references another catalog procedure by id
    When the agent follows that reference
    Then model-reachable capabilities name matt_pocock_workflow mode capability
    And disclosed references name the matt_pocock_active load action
    And required dependencies are described as already bundled
    And no procedure text calls a catalog procedure a skill, arms a skill state, runs user-invoked setup, or points at available_skills

  Scenario: Loaded references survive workflow restoration
    Given an active workflow has loaded one or more disclosed references
    When the session restores that workflow state
    Then it validates the disclosure chain in order
    And it reinjects the root procedure, mandatory dependencies, and loaded references without duplicates
    And references disclosed by the restored references remain available

  Scenario: The active gateway is progressively disclosed
    Given no Matt Pocock workflow is active
    When a session starts
    Then transition, load, complete, cancel, and interview operations are inactive
    When a workflow starts
    Then those active-state operations become available
    When the workflow reaches a terminal state
    Then those active-state operations become inactive again

  Scenario: The gateway survives its own tool disclosure write
    Given no Matt Pocock workflow is active in the session
    And the active-tool snapshot does not yet report matt_pocock_workflow
    When a session starts and the extension reconciles its tool disclosure
    Then matt_pocock_workflow is active because /matt-pocock names it
    And matt_pocock_active and matt_pocock_ask remain inactive
    And no tool the snapshot reported is dropped
    When a workflow starts and then completes
    Then the two active-state tools appear and disappear again
    And matt_pocock_workflow is active throughout

  Scenario: A stale restored workflow explicitly cancels after validation fails
    Given the session branch contains a workflow state with an unavailable procedure
    When the harness fails to restore that workflow
    Then it records a cancelled terminal workflow state for other extensions
    And it warns with the catalog-defined valid procedures for that route

  Scenario: Workflows advance through every non-user-owned next step
    Given an active Matt Pocock workflow has enough confirmed context to perform its next step
    When the current procedure completes its summary, decision, or ticket resolution
    Then it does not stop to recommend or ask whether to continue
    And it begins or transitions to the next applicable workflow work without waiting for further confirmation
    And it continues through newly unblocked AFK work until only a genuinely user-owned decision, unavailable fact, or required external action remains

  Scenario: Structured interview questions are available only during an active workflow
    Given the structured interview tool is initially active
    When the session starts without a Matt Pocock workflow
    Then the active tool list excludes matt_pocock_ask
    When the agent activates a Matt Pocock workflow
    Then the active tool list includes matt_pocock_ask
    When the workflow ends
    Then the active tool list excludes matt_pocock_ask again
    When the session restores an active Matt Pocock workflow
    Then the active tool list includes matt_pocock_ask

  Scenario: Agent asks the user questions via interactive selection tool
    Given an active grilling or interview procedure
    When the agent calls the matt_pocock_ask tool with question and options
    Then the tool presents choices using the Pi UI selection dialog
    And it supports a recommended option and custom user input

  Scenario: A recommended decision automatically adopts the recommendation on timeout
    Given an active grilling or interview procedure
    When the agent calls matt_pocock_ask with a recommended option
    And the selection times out
    Then the tool automatically selects the recommended option
    And it does not leave the decision pending

  Scenario: A decision without a recommendation has no timeout and remains pending when unanswered
    Given an active grilling or interview procedure
    When the agent calls matt_pocock_ask without a recommended option
    Then the selection dialog has no timeout
    When the selection is cancelled, Pi has no UI, or custom input is blank
    Then the tool reports that the decision is pending user input
    And it does not authorize workflow progression

  Scenario: The package has no recursively discoverable child skills
    Given pi-matt-pocock is packaged
    When Pi discovers its resources
    Then its manifest declares only the package-root extension
    And the package contains no SKILL.md file
    And its procedures remain plain Markdown resources

  Scenario: Matt Pocock tool rows use operation-specific prefixes
    Given a Matt Pocock workflow or structured interview tool result
    When Pi renders its collapsed lifecycle row
    Then a workflow row label is [matt pocock] started ·
    And a structured interview row label is [matt pocock] ask ·
    And the operation appears outside the bracketed prefix

  Scenario: Workflow activation uses the shared lifecycle row
    Given a Matt Pocock workflow tool result contains a loaded procedure for the model
    When Pi renders the user-facing workflow row
    Then it shows [matt pocock] started · followed only by the readable current phase title on the shared band
    And expanding the row shows only a distinct readable route title as a `route · value` field
    And it does not repeat the phase id as a detail
    And it does not render the procedure text as user-facing details

  Scenario: User-invoked procedure starts use the impeccable lifecycle block
    Given the user starts a catalog workflow route, transitions one, or starts a standalone capability from /matt-pocock or its menu
    When Pi renders that procedure start
    Then the head row shows [matt pocock] started alone
    And one blank band row separates that head from the block body
    And the block body is the user's own task verbatim when provided, otherwise the readable phase title or capability label
    And a multi-line task keeps every authored line on its own row on pi's native user-message band with no expand hint
    And the procedure body is delivered as a displayed procedure message rather than a user message
    And model-facing guidance and persisted workflow state remain complete and unchanged

  Scenario: Workflow lifecycle rows use the actual phase title across all routes
    Given any catalog workflow route at one of its supported phases and no user-supplied task
    When Pi renders a workflow start, procedure message, or phase transition
    Then the lifecycle subject is the readable title of that actual phase
    And a user-supplied task replaces that subject in the delivered row
    And the collapsed row contains neither a route id nor a route title
    And persisted route and phase ids remain unchanged

  Scenario Outline: Ending a workflow shows its actual terminal phase
    Given a workflow is active at any supported phase, including its entry phase
    When the agent invokes <action> through matt_pocock_active
    Then the lifecycle subject is the readable current phase title followed by <status>
    And the entire workflow ends with <status> rather than advancing to a presumed final phase
    And the terminal record preserves its route, procedure, phase, and work item identity
    And active-only tools are disabled

    Examples:
      | action   | status    |
      | complete | completed |
      | cancel   | cancelled |

  Scenario: Restored tool results use their recorded phase instead of an old route subject
    Given a saved transition, completion, or cancellation result has a route-based subject
    And its details contain the workflow state at that event
    When Pi renders that result after a reload
    Then the lifecycle subject is derived from the recorded phase and action
    And it does not use the current session's active workflow

  Scenario: No-detail lifecycle operations do not advertise empty expansion
    Given a workflow transition, completion, active reference load, standalone capability, or standalone reference result
    And its lifecycle title fits the terminal width
    When Pi renders the registered tool result
    Then the row has no expand hint or redundant action, capability, or reference fields
    And expanding it does not repeat the title or reveal model-only content or metadata
    And native Pi-kit wrapping remains responsible for titles clipped at narrower widths

  Scenario: Cancellation expands only its recorded nonblank reason
    Given a saved cancellation result records its terminal phase and a nonblank cancellation reason
    And a different workflow is now active
    When Pi renders and expands the saved result
    Then its lifecycle subject still uses the recorded terminal phase
    And its stored reason appears exactly once as a reason field
    And it does not repeat action cancel or read the active workflow state
    And model-visible content and persisted result details remain unchanged

  Scenario Outline: A cancellation without a meaningful reason has no extra details
    Given a saved cancellation result has a <reason> reason
    And its lifecycle title fits the terminal width
    When Pi renders the registered tool result
    Then the row has no expand hint or action field
    And expanding it does not add an empty reason field

    Examples:
      | reason          |
      | missing         |
      | empty           |
      | whitespace-only |
      | ANSI-only       |
      | OSC-only        |

  Scenario: Non-workflow subjects keep their own identities
    Given a standalone capability, reference load, or structured question
    When Pi renders the lifecycle row
    Then it retains the capability id, reference id, or question as its subject
    And it does not substitute an active workflow phase

  Scenario: A structured answer keeps question and answer visible in the collapsed row
    Given a Matt Pocock structured interview result contains a question and answer
    When Pi renders the collapsed ask row
    Then its first row shows the question
    And its second row shows the answer
    And the row remains expandable for non-duplicated metadata

  Scenario: A multiline structured answer renders each line cleanly without raw newlines
    Given a Matt Pocock structured interview result contains a multiline answer
    When Pi renders the collapsed ask row
    Then no rendered TUI row contains a raw newline
    And the first answer line shows the answer label
    And subsequent answer lines remain visible in separate rendered rows

  Scenario: Workflow status clears use the shared Pi-kit transient-status adapter
    Given the workflow lifecycle clears its status entry
    When a session starts, restores, ends, or transitions a workflow
    Then it clears the matt-pocock status through pi-kit's status adapter

  Scenario: Workflow notifications use the shared Pi-kit notification adapter
    Given the workflow command needs to notify the user of a status or validation outcome
    When it emits that notification
    Then it delegates notification sanitization and delivery to pi-kit

  Scenario: Packed package resolves workspace dependency protocols
    Given the package declares workspace dependencies for local development
    When the package is packed for distribution
    Then the packed manifest resolves @fradser/pi-kit to a concrete semver version
    And it contains no workspace protocol dependencies

  Scenario: The package documents its Chinese workflow-harness architecture
    Given a user needs to understand how pi-matt-pocock differs from the upstream skill collection
    When they open the package README
    Then it links to the Chinese architecture guide
    And the guide explains route selection, on-demand procedure loading, session persistence, and the schema trade-off

  Scenario: Upstream synchronization metadata is verifiable
    Given the package records its selected upstream resources and intentional exclusions
    When the upstream sync contract is checked and the package is packed
    Then the compared commit, comparison tag, and resolved tag commit are distinct fields
    And every selected upstream skill maps to a catalog capability with the recorded invocation mode
    And ignored upstream skills carry an explicit reason
    And the packed package includes the selection metadata and offline checker

  Scenario: A local-only capability stays out of the upstream selection metadata
    Given deslop is a local capability with no upstream origin
    When the upstream selection metadata is validated
    Then every selected entry still maps to an upstream skill and a catalog capability
    And the local capability is not listed as selected or excluded upstream content

  Scenario: Deferred lifecycle automation remains documented
    Given the first harness version is packaged
    When TODO.md is inspected
    Then it lists automatic session creation
    And it lists automatic teammate creation
    And it lists tool-level BDD or TDD write blocking

  Scenario: Native macOS dialog is guarded against non-macOS and SSH environments
    Given the native dialog helper
    When a dialog is requested on linux, win32, an SSH session, CI, or with PI_NO_NATIVE_DIALOG set
    Then the helper reports the native dialog as unsupported
    And macOS dialogs raise on unsupported environments and enforce a three-button limit

  Scenario: Native dialog configuration defaults to disabled and respects user opt-in
    Given a configuration file path or absence in Pi's agent directory as matt-pocock.json
    When loading the package configuration
    Then it defaults to native dialogs disabled
    And it enables native dialogs only when useNativeDialog is explicitly true
    And it resolves the path through Pi's agent directory, honoring PI_CODING_AGENT_DIR

  Scenario: Native dialog presents choice list and opens an input dialog for custom answers
    Given native macOS dialog is enabled and supported
    When the agent asks a structured question with options
    Then it presents a native choice list dialog
    And the dialog title is derived from an explicit tool title or active workflow context
    And selecting custom input opens a native text input dialog for typing the answer
    And timeout with recommendation automatically adopts the recommended option

  Scenario: The harness offers a default start-a-task entry in the menu
    Given no Matt Pocock workflow is active
    When the user invokes /matt-pocock without arguments
    Then the harness presents Start a task first alongside manual route selection
    When the user selects Start a task
    Then the harness forwards the conversation context for autonomous workflow routing and execution
    And it does not require the user to manually pick a route

  Scenario: Starting a new task supersedes the active workflow
    Given a Matt Pocock workflow is active
    When the user selects Start a task from the harness menu
    Then the harness records that the current workflow was cancelled as superseded
    And it forwards the conversation context for autonomous workflow or capability routing

  Scenario: Active workflow guidance states the exact tool contract
    Given a workflow is active
    When an agent turn starts
    Then the guidance shows the exact matt_pocock_active JSON shapes for transition, load, complete, and cancel

  Scenario: Workflow completion waits for candidate-bound verification and blocking reviews
    Given an engineering workflow has delegated implementation or blocking review Work
    When its active workflow guidance is injected
    Then completion requires the integrated candidate to be verified and all blocking reviews to have returned with findings resolved
    And outstanding results require yielding with the workflow still active
    And a completed review assignment is not treated as a PASS verdict on the implementation

  Scenario: Implementation assigns one integrated verification owner
    Given the implement procedure is loaded from the catalog
    When implementation work is divided among Agents
    Then implementers run assigned local checks and one integration owner runs shared checks
    And local check safety is established before execution
    And review and final checks use the same candidate revision
    And later changes invalidate only affected evidence and trigger applicable rechecks

  Scenario: Review is proportional and has an explicit uncommitted baseline
    Given the code-review capability is loaded from the catalog
    When the task concerns scoped uncommitted changes in a dirty worktree
    Then the confirmed conversation requirements can serve as the spec
    And the task baseline includes untracked files and excludes unrelated changes
    And Standards and Spec are separate verdicts without mandatory separate Agents
    And separate reviewers are used only when scale or independent expertise justifies them
    And related findings return to a bounded recheck with an explicitly refreshed brief

  Scenario: A review-only request ends with its report rather than implementation repairs
    Given code-review is loaded for a standalone review or a bounded reviewer assignment
    When the reviewer has inspected the candidate and completed the requested report
    Then it returns separate verdicts and findings even when the verdict is REWORK
    And it does not edit the implementation or wait for the owner to fix findings
    And remediation and implementation-delivery conditions apply only to the Leader or implementation owner

  Scenario: A recheck receives its new candidate and prior findings before assignment
    Given a completed review was pinned to an earlier candidate
    When the owner prepares a bounded recheck after repairs
    Then it preserves the prior findings outside the result that reopen clears
    And it supplies the retained baseline, new candidate fingerprint, correction delta and safe check scope in a refreshed brief
    And it updates a brief already referenced as authoritative before reopening and assigning Work
    And if the old description pins a conflicting candidate it creates a bounded follow-up with the refreshed description and a dependency on the completed review
    And it does not claim reopen, assign or the reopen reason updates the old description

  Scenario: Active gateway schemas reject undeclared fields
    Given a workflow is active
    When the agent calls matt_pocock_active with an undeclared field
    Then request validation rejects it before changing workflow state

  Scenario: Extension instances own independent workflow state
    Given two Pi extension runtimes load Matt Pocock in the same process
    When one starts a workflow
    Then only its own session receives state entries and active tools
    And the other runtime can start its own workflow independently

  Scenario: Branch navigation and compaction restore current instructions
    Given a workflow has delivered procedure instructions
    When the session navigates its tree or compacts context
    Then the current branch determines the active workflow and tools
    And the complete active procedure context is silently delivered again
    And the delivery set includes only that restored context

  Scenario: A malformed newest record does not resurrect old work
    Given an active workflow entry is followed by an incompatible or malformed workflow entry
    When the branch is restored
    Then the old active workflow is not restored
    And active-only tools remain disabled with a warning

  Scenario: Cancelled or aborted decisions never adopt a recommendation
    Given an active workflow asks a question with a recommended option
    When the user cancels or the tool is aborted
    Then the answer remains pending
    And only an actual elapsed timeout can adopt the recommendation
    And the recommendation must name one of the offered options

  Scenario: Native dialogs require explicit boolean opt-in
    Given configuration contains a string or number instead of true
    When the native dialog configuration is loaded
    Then native dialogs remain disabled

  Scenario: Standalone references disclose further references without workflow state
    Given a standalone capability discloses an optional reference
    When that loaded reference discloses another reference
    Then the gateway can load the newly disclosed reference
    And it does not persist workflow state or activate workflow-only tools

  Scenario: Catalog validation rejects ambiguous identities and eager cycles
    Given a catalog alias conflicts with an id or a required dependency graph contains a cycle
    When the catalog is validated
    Then the conflict or cycle is reported before the extension registers its gateway

  Scenario: Automatic compaction restores instructions before its retry
    Given Pi v1.0 is recovering an overflowing agent turn
    When session_compact restores an active workflow
    Then the silent procedure message is appended without starting a turn
    And restoration does not wait for the user's next prompt

  Scenario: Only the question deadline can select a timeout recommendation
    Given a question has a recommended option and a timeout
    When the UI returns no answer without the deadline firing
    Then the question remains pending regardless of elapsed clock readings
    When the deadline fires
    Then the selection is dismissed through its abort signal and adopts the recommendation

  Scenario: Disabling custom answers preserves literal option labels
    Given a question disables custom answers
    And an offered option is named Type custom answer...
    When the user selects that option
    Then it is returned as an ordinary selected answer without opening text input

  Scenario: Review evidence describes reachable execution paths
    Given an async cache has no replacement or invalidation operation
    When reviewing a rejection handler's identity guard
    Then a claimed stale-request race must include a reachable interleaving from the actual API
    And hypothetical future operations cannot establish that a guard is load-bearing

  Scenario: Cleanup reports retained findings honestly
    Given a cleanup retains a known redundant guard without a current requirement
    When verification remains green
    Then the retained finding prevents CLEAN
    And readability preferences are not described as behavioral compatibility requirements

  Scenario: A judgement call does not erase an unresolved review smell
    Given a review identifies redundant defensive code
    When no current requirement justifies keeping it
    Then the unresolved Standards finding requires REWORK even without a repository lint rule

  Scenario: Cleanup evidence distinguishes execution from reasoning
    Given a cleanup considers rejected alternative implementations
    When writing its verification note
    Then only an actually failed command is described as an observed test failure
    And an unexecuted alternative is labelled as reasoning rather than test evidence

  Scenario: Each workflow step exposes callable state controls
    Given a workflow starts or changes its active procedure
    When the model receives the state contract
    Then it includes exact transition calls for the current allowed targets and exact reference-load calls
    And a failed transition leaves the current procedure authoritative
    And an agreed task can proceed without reopening settled decisions

  Scenario: Removing an inert guard preserves the accepted grammar
    Given source analysis proves a predicate cannot change any outcome
    When a developer removes that predicate in a cleanup
    Then it does not require a new product policy or specification change
    And the final cleanup, review and handoff describe the same verified candidate

  Scenario: All lifecycle resource names use catalog display labels
    Given any standalone capability or loaded reference
    When Pi renders tool results or procedure messages, including saved results
    Then it shows the readable catalog label rather than a raw procedure id
    And workflow phases keep their readable phase titles
    And user-authored task text and persisted resource ids remain unchanged

  Scenario: Transition menus use readable names without changing targets
    Given an active workflow with legal next procedures
    When its transition menu opens
    Then its title uses readable route and phase titles
    And each choice uses the target phase title that its lifecycle row will show
    And each choice resolves to the same internal target id
