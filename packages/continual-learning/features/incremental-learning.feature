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
    Then its complete serialized object is at most 512000 UTF-8 bytes and 256 entries
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

  Scenario: Only plain assistant narration may be omitted without losing primary evidence
    Given a task exceeds the entry or byte budget
    When bounding omits only plain assistant narration
    Then report context omission without forcing proposals-only mode
    But when user, tool-result, assistant tool-call provenance or unknown-role entries are omitted
    Then report primary evidence loss and force proposals-only mode
    And retain exact citation and semantic validation in both cases

  Scenario: Malformed JSON on an empty Memory scope uses one bounded correction
    Given the selected existing Memory scope is empty
    And a completed planner returns one marked incremental plan with invalid JSON syntax
    When no cancellation, model error or output limit occurred
    Then use the existing single structural correction slot with frozen original evidence
    And never apply malformed text directly
    And corrected identities, exact citations, privacy and Jev judgments must pass
    But malformed output with an existing selected scope remains rejected

  Scenario: Damaged output cannot authorize shared new memory
    Given an empty selected scope and one syntax-damaged incremental plan
    When the bounded correction returns a project memory classified safe
    Then the parent classifies regenerated records as private before validation
    And no regenerated record is mirrored into project shared memory

  Scenario: Multiple extracted plans remain ambiguous
    Given two structured plans followed by a syntax-damaged plan
    When the child exits successfully
    Then malformed recovery does not override the extractor ambiguity rejection

  Scenario: Real-source counterevidence fits the complete wire budget
    Given 205 complete frozen pluggy entries and five cited memory candidates
    When support context and review windows are packaged for Jev
    Then every original entry is reviewed unchanged within actual wire limits
    And cited entries colocated in a window remain available by exact index
    And late or cited-window contradictions and transport failures hold the plan
    And windows are not merged using raw entry size alone

  Scenario: Unresolved source defects can be learned without inventing a recovery
    Given actual failed verification and matching inspected source establish an unresolved defect
    When Memory support is reviewed against that complete evidence
    Then a source-state-bound observation does not require a successful fix
    And temporary service faults, guessed causes and permanent failure generalizations remain held
    And confidence thresholds and complete counterevidence review remain unchanged

  Scenario: A sparse semantic repair omits an unchanged candidate array
    Given an original Memory plan contains rewrites and new proposals
    When the semantic repair returns only the rewrites and omits newMemories
    Then the parent retains every original new proposal byte-for-byte
    And the merged plan still requires complete citation, intent and semantic validation
    But an explicitly malformed candidate array remains rejected

  Scenario: One correction sees retained and proposed Memory failures together
    Given unchanged selected Memory and new proposed knowledge both fail semantic review
    When the parent prepares its one bounded semantic correction
    Then both disjoint failure scopes have been reviewed before the worker starts
    And only held retained names and held proposed fields may change
    And every combined candidate is fully revalidated before any write

  Scenario: Semantic correction preserves sources without counting redundant subquotes twice
    Given a rejected proposal retains an exact multiline source quote
    When a correction cites uniquely recoverable indentation and a contained subquote at the same index and role
    Then the parent restores exact source indentation before merging
    And retains every original citation while omitting only redundant new subquotes
    And unchanged citation bounds and full semantic validation still apply

  Scenario: A new proposal keeps a verified fact instead of an unsupported explanation
    Given complete digest-bound review passed every description check but held only the new proposal body
    When the parent constructs a distilled replacement from that exact description
    Then the original identity, privacy and citations are retained
    And existing Memory rewrites are never distilled
    And the replacement requires full combined semantic review before writing
    But missing, partial or mismatched checklists cannot enable distillation

  Scenario: Representation repair does not consume the knowledge correction phase
    Given one structural correction produces a schema-valid cited plan
    And complete review holds retained knowledge and proposed knowledge
    When the parent performs its one semantic correction
    Then the worker receives both disjoint reviewed failure scopes
    And both correction attempts and their individual costs remain in the receipt
    And the final combined plan must pass every original validation gate
    But neither phase may retry itself or start fresh planning

  Scenario: Field-specific semantic correction preserves validated source observations
    Given an existing proposal has parent-validated repository observations
    And its semantic review holds only the body or index description
    When a correction omits or changes the source observation metadata
    Then the parent preserves the original observation metadata exactly
    And only the held claim fields and their permitted citations are replaced
    And the complete corrected plan still requires semantic and mutation validation

  Scenario: Missing observations never establish the absence of repository claims
    Given selected Memory records have no validated repository observations
    When the parent expands an incremental plan
    Then their repository grounding is UNVERIFIABLE regardless of their filenames
    And it does not assert that an arbitrary filename contains no repository claim

  Scenario: Bounds repair cannot discard original repository observations
    Given a complete Memory review is refused at a bound before a field checklist exists
    And the original operation has parent-validated repository observations
    When a semantic replacement omits or replaces those observations
    Then the parent retains the original observations
    And the complete replacement still requires ordinary validation and semantic review

  Scenario: Structural repair can restore a missing new proposal filename suffix
    Given a new Memory proposal has a valid filename stem but omits .md
    When structural correction supplies exactly that suffix without a collision
    Then the parent recognizes the original new proposal identity and privacy
    And existing mutation targets cannot be renamed by that correction
    And ordinary filename, citation, semantic and write validation still apply

  Scenario: Semantic correction preserves multi-fact predecessor knowledge
    Given a rejected rewrite whose body retains several independently supported predecessor facts and an unresolved verification failure
    When the parent requests its bounded semantic correction
    Then only the index description is constrained to one supported clause
    And the complete predecessor and original operation remain in the correction input
    And shortening the body does not authorize discarding still-valid knowledge or independently supported failure observations
    And the corrected plan still requires complete preservation and semantic review

  Scenario: Optional description distillation does not overwrite an actual failure correction
    Given a held new Memory proposal whose original description completed review
    And the bounded correction changes its body to preserve the observed source state or corrects its citations
    When the parent considers optional description distillation
    Then it keeps the corrected content and citations unchanged
    And the complete corrected plan still requires all final validation

  Scenario: Complete corrected knowledge is not refused because comparison context repeats citations
    Given a real corrected Memory plan whose complete body and citations must survive distillation
    When review compares every exact replacement with the exact predecessor records
    Then other proposals carry indexed role and quote-digest associations instead of repeating quotations
    And each proposal receives its full original quotations and complete cited source in its own support review
    And all original evidence is reviewed byte-for-byte without changing request or semantic limits

  Scenario: Deferred newer feedback prevents stale prefix learning
    Given an independently digest-verified same-task feedback extension of an older pending slice
    And the extension is deferred by its existing retry or attempt limit
    When bounded backfill considers the older slice
    Then no learning call uses the obsolete prefix alone
    And both original references and all attempt limits remain intact
    And changed or unverified extensions do not suppress unrelated work

  Scenario: Larger verified citations preserve protected claims without duplicate overflow
    Given a field correction with eight valid citations and a protected original description
    And a new quote contains an original quote verbatim at the same source index and role
    When the parent merges the corrected body and its sources
    Then the larger quote retains every original and corrected source byte
    And evidence at different indexes or roles remains distinct
    And the original eight-citation limit and complete semantic review remain required

  Scenario: Correcting a stored contract preserves mutation context in index review
    Given a stored wrapper contract has been superseded by an observed successful source edit
    When its proposed rewrite body and index description are reviewed separately
    Then the description retains the parent-validated rewrite action and target
    And its content is still judged independently of the proposed body
    And uncertain description judgments remain held at the unchanged threshold
