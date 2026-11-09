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

  Scenario: A Memory call produces one started row and one final result row
    Given a learn call starts exactly one Memory pipeline
    When the run ends
    Then the transcript shows one [learning] started row
    And one final outcome row that expands to Markdown descriptions and bodies of applied safe Memory
    And the complete receipt stays unchanged in message details and on disk
    And an applied write has an undoable learning-history record
    And no settled or early-correction hook starts a second pipeline for the task

  Scenario: A started run always reports its outcome, including a no-change result
    Given a learn call emits a [learning] started row but finds no durable changes, screens nothing, or organizes in process
    When the parent finishes that pipeline and returns a receipt
    Then the transcript shows exactly one final [learning] outcome row for that batch
    And the row names the no-change, screened, skipped or organized outcome honestly
    And no started row is left without its paired outcome row
    And the tool result text and the outcome row describe the same receipt

  Scenario: A cancelled started run still reports its terminal outcome
    Given a learn call emitted a [learning] started row
    And the session shuts down or changes while the pipeline is still running
    When the parent writes the cancelled receipt
    Then the transcript shows one [learning] outcome row naming the cancellation
    And no started row is left without a paired outcome row
    And the tool result reports the session change honestly without claiming applied knowledge

  Scenario: The learn tool result row names the applied Memory count
    Given a learn call applied two validated Memory records
    When its tool result is rendered as a settled row
    Then the row says "learned 2 Memory changes", not "learned 0 Memory changes"
    And the count comes from the same receipt that produced the final outcome row
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
