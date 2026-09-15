Feature: Spend learning tokens only when durable value is plausible
  Automatic learning uses deterministic screening before any model call, shares one
  selector-built authoritative dossier, and accounts for every worker attempt.

  Scenario: Parent screening can skip an automatic run without tokens
    Given a frozen task contains no durable user statement, correction, or harness event
    When automatic learning evaluates the task
    Then no selector or planner is launched
    And the receipt records zero calls and zero tokens

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
