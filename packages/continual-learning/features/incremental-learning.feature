Feature: Select the minimum sufficient scope for incremental learning
  Routine continual learning works from one completed task and bounded Memory
  metadata, then constructs one authoritative dossier without broad discovery.

  Scenario: Explicit continuation retains the original task evidence
    Given a task has an original request and tool evidence
    And the user says continue or retry, including a chain of such continuations
    When the parent constructs the completed Task Slice
    Then it includes the original request and evidence through the latest result
    But a new substantive request and an undelivered queued request do not extend that task

  Scenario: Task evidence stays within its serialized byte bound
    Given one task contains an oversized intermediate or final entry
    When the parent constructs the Task Slice
    Then its complete serialized object is at most 512000 UTF-8 bytes and 96 entries
    And the original request is retained without changing evidence text
    And omitted entries are explicitly counted
    And fitting recent evidence and the final result are retained
    But an original request that cannot fit fails explicitly before learning

  Scenario: Explicit incremental consolidation always reaches selection
    Given the current task has no automatic screening keywords
    When the user invokes /consolidate
    Then one incremental selector is called
    And its no-op selection starts no delta planner
    And no full-corpus fallback occurs

  Scenario: Every selector exit releases its run
    Given incremental selection fails, is cancelled, throws, or selects no phases
    When that learning pipeline finishes
    Then its project lock is released
    And another consolidation in the same process can start
    And session shutdown leaves no owned lock

  Scenario: The current task slice excludes history and a queued later task
    Given a session contains earlier completed tasks, one completed current task, and a queued later user task
    When the parent constructs the current Task Slice
    Then it contains the current user request, tool activity, extension continuations, and final assistant result
    And it excludes earlier tasks and the queued later task

  Scenario: The selector receives metadata without Memory bodies
    Given current-task evidence and a Memory index with classifications, types, and descriptions
    When incremental Memory selection starts
    Then the selector prompt contains the Task Slice and bounded Memory metadata
    And it does not contain Memory bodies, read paths, broad repository discovery instructions, or tools
    And it requires the minimum sufficient scope

  Scenario: Selection has no arbitrary candidate-count cap
    Given more than eight Memory entries are genuinely related to the task
    When the selector returns every exact related name
    Then the parent accepts every selected entry within the existing corpus safety bounds

  Scenario: New Memory can be planned from an empty existing scope
    Given the current task contains new durable evidence
    And the selector chooses no existing Memory
    When the parent builds the Learning Dossier
    Then the dossier contains the Task Slice and an empty selected Memory list
    And Memory planning remains enabled

  Scenario: An echoed input field does not discard a matched selection
    Given the selector echoes a Task Slice field such as omittedEntries beside the eight response fields
    When its digest matches this run and every authoritative field validates
    Then the parent accepts the selection instead of ending the run with zero operations
    But a response missing a required field is rejected and the rejection names the missing field

  Scenario: Selector routing cannot suppress deterministic durable evidence
    Given the parent screen identifies durable Memory or Harness evidence in the Task Slice
    When the selector omits that phase from its routing flags
    Then the parent keeps the deterministically selected phase enabled

  Scenario: Harness activity means Harness-owned transcript evidence
    Given a tool result only mentions policies, harness files, or guarded words
    When the parent screens the Task Slice
    Then it claims no Harness activity
    But a guardrail entry, Harness guidance delivery, or Harness note marker is activity

  Scenario: A reviewed selector verdict is not overridden by tool noise
    Given a manual consolidation reaches selection
    And the selector declines phases after reviewing this same Task Slice
    When that slice only carries a verified tool recovery or Harness activity
    Then the declined phases stay disabled and no planner starts
    But user-stated durable evidence or a constraint still floors the selector

  Scenario: Selector failure is fail-closed
    Given the selector times out, returns ambiguous objects, or names unknown Memory
    When the parent validates the selector result
    Then incremental selection fails without writing a dossier
    And it does not fall back to reading every Memory body or full mode

  Scenario: A verbose selector response may contain one balanced object
    Given the selector wraps one valid selection object in prose or a code fence
    When the parent parses the selector response
    Then the exact selection is accepted
    But multiple balanced selection objects are rejected as ambiguous

  # The reason is diagnostic prose inside a bounded artifact. An explanation
  # longer than the bound is a formatting overflow, not a structural violation:
  # rejecting it discarded a whole valid selection and ended the run.
  Scenario: An over-long selector explanation is bounded instead of fatal
    Given the selector returns a valid selection whose reason exceeds the parent bound
    When the parent validates the selector result
    Then the selection is accepted with a reason inside the bound
    And a non-string reason or any structural violation still fails closed

  Scenario: Memory management points to the shipped planner
    Given a headless user opens memory management
    When the command reports its consolidation procedure
    Then the path names the package-owned incremental planner in prompts
    And the referenced Markdown file exists in the installed package

  Scenario: Planner tasks bind one authoritative identity block
    Given a full or incremental Memory plan is requested
    When the parent builds the child task
    Then run identity and input paths are defined once by the mode-specific prompt
    And the task header supplies only task-specific scope, mode, and rejection feedback
    And the planner still returns a parent-validated bounded plan or a no-op

  Scenario: The authoritative dossier contains selected evidence once
    Given the selector chooses related existing Memory
    When the parent writes the Learning Dossier
    Then the Task Slice appears once
    And each selected Memory body appears once
    And unselected Memory bodies do not appear

  Scenario: The dossier records Harness events the Harness surface produced
    Given the Task Slice contains a recorded guardrail decision or a Harness note
    When the parent writes the Learning Dossier
    Then each Harness event appears with its decision and recorded prose
    But repository or conversation text that merely names the harness is not an event
