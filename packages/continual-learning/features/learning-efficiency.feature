Feature: Spend learning tokens only when durable value is plausible
  Automatic learning uses deterministic screening before any model call, shares one
  selector-built authoritative dossier, and accounts for every worker attempt.

  Scenario: Empty Memory routes explicit automatic evidence without a selector model
    Given the indexed Memory corpus is empty and the user states durable facts or preferences
    When automatic learning selects its scope
    Then the parent selects no existing bodies and routes its evidence-backed phases without a model call
    And planners still propose changes for parent validation against the frozen dossier
    And nonempty indexes and ambiguous tasks still use the metadata selector

  Scenario: Headless selector failure retains a safe diagnosis
    Given a selector returns a malformed selection containing private output
    When the parent rejects it and writes the pipeline receipt
    Then the selector attempt records the parent-generated rejection category
    And the receipt does not copy raw model output or worker stderr

  Scenario: Incremental learning carries evidence instead of reasoning transport
    Given a completed task contains long assistant reasoning and provider metadata
    When the parent freezes its incremental evidence
    Then user and tool entries remain byte-identical with the same evidence indexes
    And assistant visible text and tool calls remain available for context and touched paths
    But assistant reasoning, signatures and usage metadata are excluded
    And the original session is unchanged
    And explicit full maintenance keeps its complete-session scope

  Scenario: Empty full maintenance does not spend model tokens
    Given a new session contains only model and thinking settings
    And the project has no existing Memory entries
    When the user requests full maintenance
    Then no selector or planner is launched
    And the result says there is no learning input rather than claiming a reviewed no-op

  Scenario: Full maintenance can bootstrap knowledge
    Given the existing Memory corpus is empty
    And the frozen session contains a durable private preference and shared project fact
    When the full Memory planner reviews the evidence
    Then it proposes both new memories independently of the empty selected scope
    And each proposal uses its exact literal kind and indexed evidence

  Scenario: A fresh full run can use recent project evidence
    Given the current session contains no user or tool evidence
    And a recent stored session has real evidence for this exact canonical project
    When the parent prepares full maintenance
    Then it freezes the latest eligible session's active branch using Pi's projection
    And the receipt identifies that source and its digest
    And other projects, symlinks, oversized files and edited-away evidence are excluded
    But automatic and incremental learning still use only their current task

  Scenario: Full knowledge does not require an invented Harness rule
    Given the frozen full input contains only project facts and personal response preferences
    When the Harness planner finds no supported execution constraint
    Then it returns an identity-bound plan with empty operations and evidence arrays
    And it does not omit operations or invent a text rule for the personal preference

  Scenario: Harness recovery preserves every attempt in the receipt
    Given a Harness planner returns no structured plan and its one repair succeeds
    When the parent completes the learning phase
    Then the receipt retains the initial rejected attempt and the repaired attempt
    And totals include both workers' reported usage and cost
    And the receipt reports exactly one retry

  Scenario: Tool-verified recovery is a Memory candidate
    Given a tool reports a failure and a later tool verifies a successful build or test
    When automatic learning screens the task
    Then Memory selection is enabled without requiring a user keyword
    But an assistant claim, an unrelated successful read, or a still-failing task is insufficient
    And the recovery alone does not enable Harness or AGENTS.md changes

  Scenario: AGENTS.md-only changes are visible in the terminal title
    Given a consolidation applies only AGENTS.md operations
    When its result is rendered
    Then the title names the number of AGENTS.md changes
    And it never reports no durable changes

  Scenario: Parent screening can skip an automatic run without tokens
    Given a frozen task contains no durable user statement, correction, or harness event
    When automatic learning evaluates the task
    Then no selector or planner is launched
    And the receipt records zero calls and zero tokens

  Scenario: Screening keeps knowledge and executable-validation opportunities distinct
    Given the user explicitly records a project fact or asks to retain a preference
    When automatic learning screens the frozen task
    Then Memory is eligible to propose untrusted reference knowledge
    And a question that merely asks what to do does not create a learning opportunity
    Given the user asks for a regression test or invariant
    When automatic learning screens the frozen task
    Then Harness is eligible to propose an executable check
    And the screen does not treat the requested check as Memory knowledge by itself

  Scenario: Automatic learning is lightweight
    Given automatic learning finds durable evidence
    When it selects phases
    Then it limits the run to evidence-backed incremental phases
    But only an explicit /consolidate full keeps exhaustive maintenance behavior

  Scenario: Later planners share the selector dossier
    Given Harness and AGENTS.md both have evidence candidates
    When their planning begins after incremental selection
    Then the selector-built Learning Dossier remains the bounded immutable authority
    And both planners receive the same dossier digest instead of independently exploring the full context or repository
    And Harness and AGENTS.md planning may overlap
    But their validated mutations are applied sequentially

  Scenario: Quoted task instructions never become the worker's current assignment
    Given task evidence includes a previous user's reply-only instruction or an embedded plan
    When any selector or planner worker starts
    Then a package-owned system instruction identifies evidence as untrusted data
    And the worker follows the parent output protocol and current identity instead
    And the selector's JSON example contains its exact bound context digest
    And rejected selections report a specific bounded structural reason without echoing evidence

  Scenario: Retry policy preserves value
    Given a planner attempt fails
    When the parent classifies the failure
    Then default incremental learning classifies one pre-mutation Memory syntax or validation failure as an incremental Memory repair
    And incremental Harness and AGENTS.md planners do not retry
    And explicit full learning may temporarily classify one pre-mutation syntax or validation failure as a full planner retry
    And provider, timeout, cancellation, output-limit, stale-input, and post-mutation failures never retry

  Scenario: Routine learning feedback is quiet in the transcript
    Given automatic learning screens out a task or completes a verified no-op
    When the pipeline settles
    Then it does not create a routine notification row
    But selector, planner, or apply failures still notify with a recovery-oriented message
    And explicit /consolidate produces one compact terminal learning event
    And expanded event details contain phase outcomes and token categories

  Scenario: The terminal learning title names applied surfaces
    Given an explicit consolidation applies Memory and Harness operations
    When the terminal learning event is rendered
    Then its title reports singular or plural Memory counts
    And its title reports singular or plural Harness change counts
    And mixed Memory and Harness counts are joined with and
    And it does not replace those surface counts with a generic change count

  Scenario: Learning reports every token category and unavailable provider cost
    Given selector and planner workers finish with usage metadata
    When the pipeline settles, rejects a phase gate, or fails after attempts begin
    Then a receipt records each attempt outcome, duration, operations, retries, input, output, cacheRead, cacheWrite, total tokens, and cost
    And failed Memory attempts are persisted even when the worker cannot be configured, prepared, resolved, or spawned
    And failed Memory attempts are persisted when later phases cannot start
    And the user receives a compact totals summary with every token category displayed separately
    But nonzero usage with zero provider-reported cost is displayed as cost unavailable rather than a zero-dollar cost
