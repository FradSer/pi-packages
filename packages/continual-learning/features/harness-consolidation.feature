Feature: Harness consolidation alongside memory consolidation

  One /consolidate invocation runs a parent-owned pipeline: the established
  read-only memory planning phase, followed by a harness phase that mines the
  same immutable session snapshot for tool-call guardrail evidence (blocked
  calls, confirm outcomes, user corrections) and applies bounded changes only
  to the project harness.json layer. The harness phase never mutates
  memory results and never writes shared config layers.

  Scenario: Harness tests isolate configuration and runtime artifacts
    Given a Harness test uses a temporary project and agent root
    And the caller's ambient global Harness configuration may be invalid
    When it resolves configuration or creates its consolidation run
    Then it reads only the disposable user and project layers
    And its run directory is below the temporary agent directory
    And it leaves the real user agent directory untouched

  Scenario: /consolidate consolidates both surfaces
    Given manual consolidation completes successfully with context captured
    When the memory phase reports a verified consolidation
    Then a harness planning phase starts against the same session history
    And its plan is validated against the same run identity fields

  Scenario: Harness planning uses a package-owned minimal read-only prompt
    Given the pipeline starts harness consolidation
    When the package launches the harness planner
    Then its instructions come from the package-owned prompts/harness-consolidator.md resource
    And its typed builder binds every required identity value
    And the child disables extension, skill, prompt-template, context-file, and theme discovery
    And the child receives only read, grep, find, and ls tools
    And the parent remains the only process allowed to apply harness changes

  Scenario: The harness planner consumes the authoritative task dossier
    Given the current task contains blocked tool calls, confirmation outcomes, or user corrections
    And the selector wrote the authoritative Learning Dossier
    When the Harness planner starts
    Then its task names that dossier and the immutable task-slice snapshot
    And it does not run an independent model explorer or broad repository scan
    And every proposed operation cites concrete observed evidence from that snapshot
    And the parent alone writes any configuration

  Scenario: Harness evidence is bound to an observed actor and quote
    Given a harness operation cites a user requirement, user correction, or tool outcome
    When the parent validates the operation against the immutable snapshot
    Then each evidence item carries a verbatim quote found in the snapshot
    And each evidence item identifies source "user" or "tool"
    And model-only speculation or an invented paraphrase is rejected

  Scenario: SDK tool-result messages provide tool evidence from content
    Given the immutable snapshot contains an SDK message with role "toolResult"
    When the parent validates a harness operation against that snapshot
    Then a quote from the tool-result content is accepted as source "tool"
    And a quote from the tool name or envelope metadata is rejected
    And assistant message content remains ineligible as tool evidence

  Scenario: Flat rule learning requires executable positive and negative cases
    Given an addRule or updateRule operation carries one rule with an id and skill, bash, or text selector
    When the parent evaluates bounded positive and negative fixtures with the actual selector evaluator
    Then every positive case matches with its declared Bash action when applicable
    And every negative case remains unmatched
    And unknown skills, missing cases, failing cases, or legacy operations reject the plan before any write
    And skill and text guidance cite narrow user or tool evidence for their actual scope

  Scenario: Automatic learning protects explicit and manually authored rules
    Given an existing rule comes from built-in defaults, another layer, or an unmarked project entry
    When consolidation proposes to disable it or weaken its action or match scope
    Then the operation is rejected because automatic learning cannot disable or weaken existing rules
    And a user-looking quote or model authorization field cannot change that result
    And a project rule marked as learned may be revised only with grounded evidence and passing cases
    And learnedRules metadata binds its id to the current rule revision
    And manual edits invalidate automatic ownership even if old metadata remains
    And identity conflicts in any layer include disabled and invalid declarations
    And selector changes, re-enabling and weaker execution conditions require explicit authorization

  Scenario: Oversized non-plan telemetry does not abort harness consolidation
    Given child output contains an oversized non-plan message_update event followed by a valid final plan
    When the harness phase extracts the child plan
    Then the oversized telemetry event is ignored
    And the valid final plan is still validated and applied autonomously
    And the user receives no warning about the ignored telemetry event

  Scenario: Harness operations are bounded
    Given a harness plan declares more than the configured maximum operations
    Or a single rule payload exceeds the configured byte bound
    When the parent validates the plan
    Then the plan is rejected and no harness file is modified

  Scenario: Legacy configuration coexists with new learning without migration
    Given a target contains valid policies, disabled names or skillPrompts
    When runtime loading encounters it
    Then existing protections remain active and loading preserves actual file bytes
    When automatic learning adds a non-conflicting flat rule
    Then legacy containers and provenance remain structurally unchanged
    And old policy and disabled identities are reserved against automatic replacement

  Scenario: Harness plans bind to the run identity
    Given a harness plan whose runId, scopeDigest, or artifactHash disagrees with the run
    When the parent extracts the plan
    Then the plan is rejected before any validation of its operations

  Scenario: Application targets only the project layer atomically
    Given a schema-valid harness plan
    When the parent applies it
    Then changes merge into <project>/.pi/harness.json in one atomic write
    And the user shared and project personal layers are never written
    And a pre-apply receipt records the prior file digest and a post-apply receipt records the final digest

  Scenario: Failed readback after replacement rolls back only the parent's own candidate
    Given a complete validated candidate replaces an existing or missing target atomically
    When readback fails before a verified result or post receipt
    Then both direct application and pipeline application report failure
    And if the current bytes still equal that candidate the exact predecessor is restored
    And a previously missing target is removed instead of left partially applied
    And an external replacement is preserved rather than overwritten during rollback
    And a failed pipeline creates no post receipt

  Scenario: Harness planner termination is awaited before the phase finishes
    Given the harness planner child has been spawned
    When the planner times out, exceeds its stdout limit, or is cancelled after spawn
    Then the parent awaits child termination and the child close event
    And the planning result does not resolve while the child could still hold the consolidation run

  Scenario: Harness phase failure isolates from memory results
    Given the memory phase already applied and verified its results
    When the harness phase fails to produce a valid plan or fails to apply
    Then memory results remain untouched
    And the user receives a harness-specific diagnostic instead of an overall failure

  Scenario: no-context skips the harness phase
    Given the user invoked /consolidate no-context
    When the memory phase finishes
    Then no harness planner child is spawned
    And the user is informed that harness consolidation needs captured context

  Scenario: Concurrent invocations stay single-flight across both phases
    Given a consolidation pipeline is running in either phase
    When another /consolidate is triggered
    Then no second planner child is started
