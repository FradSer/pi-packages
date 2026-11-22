Feature: One model-facing learning tool
  The model calls one zero-argument tool when the user asks for learning. The
  parent owns evidence freezing, classification, every validation gate, writes,
  receipts and undo. The model supplies no intent, type, content or path.

  Background:
    Given the pi-continual-learning package is installed
    And the task evidence is frozen by the parent before any route decision

  Scenario Outline: Explicit learning requests keep their real user entry
    When the user enters "<prompt>"
    Then that text remains a real role:user entry in the session
    And the model calls learn exactly once with no arguments
    And no other learning tool is called for the same task
    Examples:
      | prompt                     |
      | 整理记忆                    |
      | 记住这个                    |
      | 以后禁止 npm                |
      | 纠正旧规则                  |

  Scenario: The parent classifies the request, not the model
    Given the model has called learn
    When the parent selects an entry route
    Then it reads only the last real role:user entry
    And the route decision does not depend on any tool argument
    And Memory is treated as untrusted discovery context, never authority
    And screenLearningEntries keeps its own frozen evidence truth table

  Scenario: An explicit Harness request opens the guarded procedure
    Given the user asks "以后禁止 npm", "纠正旧规则" or to add a lasting rule
    When learn returns
    Then its status is authoring-started, not applied
    And the identical /harness guarded procedure is opened
    And no Memory pipeline, planner or Memory mutation runs
    And the outcome never claims a rule was added
    And the follow-up turn's write keeps exact candidate/predecessor bytes,
        positive and negative cases, no-UI fail-closed, option confirmation,
        atomic readback and rollback
    And the settled learner does not author a second rule for the task

  Scenario: Lasting preferences are Memory, not executable Harness rules
    Given the user asks to remember a durable personal preference for future replies
    When the learn tool classifies the real user entry
    Then it routes the request to Memory
    And it does not open an executable-rule authoring procedure
    And an explicitly temporary, no-remember or one-turn instruction remains unstored

  Scenario: A constraint prompt keeps its frozen both-surface evidence screen
    Given the user prompt is "以后禁止 npm"
    When screenLearningEntries screens the frozen task slice
    Then it still selects Memory and Harness
    And that truth table is neither narrowed nor reclassified
    And the tool's narrower entry route does not change those historical proofs

  Scenario: An explicit organize request stays in-process
    Given the user prompt is "整理记忆"
    When no durable knowledge signal is present
    Then the parent organizes in process without a planner or review worker
    And the result is reported honestly as organized, not as applied
    And its plain-text outcome describes file checks, not semantic organization

  Scenario: A Memory call produces one final result row
    Given a learn call starts exactly one Memory pipeline
    When the run ends
    Then the transcript shows one plain-text learning result for that run
    And the result uses Pi's native plain Text component without a lifecycle label or expansion hint
    And applied Memory filenames, descriptions and bodies are readable without expanding
    And Ctrl+O does not change the learning result
    And private entries remain visible to their owner while sensitive text stays hidden
    And applied body paragraphs, filename-like lines and literal separators stay inside their original record
    And display JSON is byte-bounded before decoding and refuses invalid Memory filenames
    And the complete receipt stays unchanged in message details and on disk
    And an applied write has an undoable learning-history record
    And no settled or early-correction hook starts a second pipeline for the task

  Scenario: A no-change run still reports one final result row
    Given a learn call finishes a pipeline that writes no changes, screens nothing, or organizes in process
    When the parent returns a receipt
    Then the transcript shows one plain-text outcome for that batch
    And the no-model organization outcome says "Memory files checked. No changes."
    And it shows no frozen-entry count, generic verification paragraph or usage metadata
    And the tool result text and the outcome row describe the same receipt

  Scenario: A cancelled run reports its terminal outcome
    Given the session shuts down or changes while a pipeline is running
    When the parent writes the cancelled receipt
    Then the transcript shows one plain-text result naming the cancellation
    And the tool result reports the session change honestly without claiming applied knowledge

  Scenario: Backfill replay reports one final result row
    Given an explicit /consolidate backfill processes a verified pending reference
    When the replay finishes
    Then the transcript shows one plain-text result for that batch
    And the replay result is not duplicated by the tool result row

  Scenario: The learn tool result stays model-facing for a paired run
    Given a learn call produced a pipeline receipt and its final receipt row
    When its tool result is rendered
    Then no duplicate learn tool result row appears in the transcript
    And the full outcome text stays available to the model
    And no additional learn tool result row repeats a non-pipeline outcome

  Scenario: The learn tool result names the applied Memory count
    Given a learn call applied two validated Memory records
    When the model receives its tool result text
    Then the text names the same applied count as the final outcome row
    And a no-change result still names zero changes honestly

  Scenario: Held, disabled and failed outcomes are reported honestly
    Given a safety gate holds, the trigger is disabled, or a run fails
    When learn returns
    Then its status names held, disabled or failed
    And it is not reported as applied, no-change or finished with issues
    And no Harness or AGENTS.md write occurs on a Memory-only route

  Scenario: A Harness write keeps the guarded-write invariants
    Given the follow-up turn will write a Harness rule
    When the parent evaluates and writes it
    Then positive and negative cases are evaluated by the parent
    And exact candidate bytes and exact predecessor bytes are bound
    And no-UI fails closed and the option-style confirmation runs
    And the write is atomic with readback and rollback

  Scenario: The declared Harness write produces a receipt and an undoable record
    Given an active /harness procedure activates the declared harness_write tool
    When the parent applies one case-validated, confirmed, atomic write
    Then the applied write emits a learning receipt and an undoable history record
    And the learn outcome still reports authoring-started, not a terminal rule write
    And the legacy two-step native write remains a separate, still-available path

  Scenario: Every authoring writer preserves existing execution protection
    Given a valid preview and an existing legacy write policy
    When harness_write evaluates the same target and content as native write
    Then the existing block or confirmation applies to both paths
    And native authoring without UI never consumes its preview or writes
    And invalid inherited layers prevent a successful authoring write
    And inherited confirmation is decided before the final write confirmation
    And policy evaluation preserves the submitted native path spelling
    And only policies matching this write require inherited confirmation
    And every raw inherited layer is rechecked after confirmation and before replacement
    And confirmation shows the complete candidate and effective rule sources

  Scenario: A failed authoring readback rolls back only its own write
    Given the authoring writer replaced an unchanged predecessor atomically
    When its readback fails with a local I/O error and no external edit
    Then the exact predecessor bytes and permissions are restored before history closes
    And no applied receipt or pending mutation remains
    But an external byte or permission change during rollback remains untouched and pending

  Scenario: Explicit authoring shares mutation ownership
    Given an approved candidate bound to predecessor bytes and permissions
    When the shared target queue or project consolidation lock is occupied
    Then the writer cannot mutate outside those boundaries
    And predecessor drift after confirmation is preserved
    And a foreign edit during readback is never overwritten by rollback

  Scenario: Cancellation follows the actual authoring commit boundary
    Given a confirmed authoring write with successful readback
    When cancellation arrives after the mutation commits
    Then the file and applied history remain consistent with the applied receipt
    And the outcome reports the actual applied change
    And receipt metadata, if saved, agrees with the applied history
    And a receipt save failure is reported as missing evidence, not as a saved receipt

  Scenario: An ordinary task does not start learning
    Given the user asks a one-off question that merely mentions "remember"
    When the model does not call learn
    Then no pipeline, planner, worker or receipt starts
    And if the model calls learn anyway, the parent returns an honest no-op without a pipeline

  Scenario: Planner-child internal contracts stay unchanged
    Given a planner child is spawned
    Then the nine --learning-* structured-output flags remain
    And planner-json-output.ts remains the structured-output gate
    And the learning_read string remains a frozen-dossier evidence marker
    And frozen proofs, fixtures and SHA256 manifests remain byte-identical
