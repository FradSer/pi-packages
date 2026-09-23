Feature: Control and inspect learned changes without changing existing defaults
  Scenario: Automatic phase policies are explicit and backwards compatible
    Given no phase policies are configured
    Then Memory, Harness and AGENTS.md keep their existing automatic apply behavior
    When a user sets a phase to propose or off
    Then automatic learning records a validated proposal or skips that phase respectively
    And a selector cannot override an off phase
    And explicit consolidation still validates and applies current plans
    And the existing AGENTS.md disabled setting remains authoritative

  Scenario: Proposals do not mutate learned surfaces
    Given an automatic phase is configured to propose
    When a valid plan is produced
    Then its plan is recorded privately with a proposal outcome
    And Memory mirrors, Harness configuration and AGENTS.md remain unchanged
    And extraction into another non-applying surface is also proposed rather than applied

  Scenario: Learned mutations have inspectable predecessors and successors
    Given a phase applies validated changes
    Then private history records only that mutation's allowed target files and exact before/after bytes
    And history and proposal records can be inspected by id
    And no-op phases do not create change records
    And sensitive material is rejected before proposal or snapshot history is saved
    And creating a previously missing private root keeps history scope stable
    And project root aliases resolve to the same scope without accepting symlinks inside learned surfaces
    And a rejected Harness mutation reports its bounded non-sensitive reason

  Scenario: Sensitive detection refuses credentials instead of ordinary text
    Given a learned surface contains ordinary prose, wiki links or workflow permission names
    When a phase snapshots or proposes that text
    Then the record is written and the mutation applies
    But a real credential, private key or provider key format in the same text is still refused

  Scenario: Explicit undo preserves later user edits
    Given a user requests undo of one applied history id
    When every target still matches that record and the user approves its preview
    Then all recorded predecessors are restored under the project lock
    And repeated undo does not apply again
    But any changed file, symlink, foreign project, invalid record or privacy violation refuses the whole undo
    And a failure during restoration rolls back already restored files
    And headless undo requires an explicit id and --yes

  Scenario: Interrupted undo is recovered without adopting unrelated changes
    Given an undo stopped after restoring only some files
    When the next learning session starts
    Then it restores the recorded successors and marks the change applied again
    But any file outside both recorded versions blocks recovery
    And rejected mutations never label another actor's changes as applied learning
    And recovery refuses private metadata or body leaks in either Memory root
    And another undo cannot replace an unresolved recovery journal

  Scenario: An interrupted mutation does not authorize unknown bytes
    Given an applied phase stopped before recording its verified outcome
    When its pending history differs from any recorded predecessor including file modes
    Then subsequent learning is blocked with an inspection hint
    And existing AGENTS.md transaction recovery runs first under the project lock
    When all pending targets are reconciled to their exact predecessors
    Then the record is marked abandoned without attributing later edits to learning

  Scenario: Independent rule evaluation uses held-out user fixtures
    Given a user-authored suite labels expected Bash decisions, skill and text matches
    When the evaluator compares the supplied baseline and candidate configurations
    Then it reports accuracy, false blocks, missed protections and regressions for both
    And it evaluates no planner-generated cases and executes no shell command
    And its report identifies configuration and suite digests
    And it does not claim model-task success or unmeasured provider savings

  Scenario: Paired task evaluation measures actual model outcomes separately
    Given a held-out suite contains fixed prompts and required or forbidden answer text
    When the explicit task evaluator runs baseline and learned Memory snapshots
    Then each arm uses a fresh disposable project with automatic learning disabled and only the read tool
    And the report contains each arm's task success, regressions, latency and observed token usage
    And configured authentication is copied privately without modifying the source
    And zero reported price with nonzero usage is marked unavailable
