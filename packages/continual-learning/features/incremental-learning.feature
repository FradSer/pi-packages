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

  Scenario: Initial source excerpts use the parent's collected source grant
    Given a frozen Memory task includes a successful parent-collected project source read
    When initial generation or the existing structural correction selects that exact source excerpt
    Then the parent passes its own source-entry bindings to the existing excerpt materializer
    And the private record contains the original source bytes
    And missing grants, changed sources and model-supplied audit flags grant no access
    And original read and edit excerpts keep their existing validation

  Scenario: Initial project knowledge combines exact source with supported context
    Given a parent-audited source declaration and separate applicability evidence
    When a new safe or private project record selects source and explanatory body units
    Then the parent copies the original declaration bytes without model reserialization
    And the complete body retains its ordered explanation and complete citation catalog
    And source selections require the original source grant and current regular file
    And user-stated project facts may use text units without source copying
    And source copying grants no public sharing permission
    And mixed field shapes, invalid indexes and oversized bodies are rejected
    And all existing source, privacy, description, body and coverage gates remain required
    And exact copying alone does not establish complete relations or later task benefit

  Scenario: Fresh project generation cannot use the legacy reader as its output contract
    Given a fresh project proposal returns legacy content instead of knowledge units
    When the parent receives that raw output before source materialization
    Then the parent retains its bound original candidate without reasoning text
    And sensitive original candidates retain hashes only
    And the existing single structural correction can return valid knowledge units
    And a correction that repeats the legacy shape fails without a Memory write
    And preference prose, retained corrections and historical legacy reads remain compatible
    And all source, privacy and semantic gates remain required
    And valid generation framing alone does not establish complete knowledge or learning benefit

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
    Given the Task Slice contains a recorded guardrail decision, handler result or Harness note
    When the parent writes the Learning Dossier
    Then each Harness event appears with its decision or bounded recorded outcome
    And behavior summaries retain exact call and matched-rule revision bindings with explicit omissions
    And handler results keep unknown timing and task outcomes distinct from task success or benefit
    And the original behavior entries remain unchanged in the Task Slice
    But repository or conversation text that merely names the harness is not an event
    And unknown event versions or decisions cannot supply a verified outcome

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
    And an unknown cause does not erase source-established conditions at the failed assertion
    And the record keeps reusable conditions rather than a task log or a guessed cause
    And stateful knowledge identifies resource or result ownership, changing events and unchanged state
    And material default or selected branches keep their source-backed consequences
    And generation and coverage keep scope, guards, observation phase and unresolved relations
    And observed version or revision identifiers that bound a lesson stay in the body with their citations
    But an unavailable source identifier does not erase another independently observed identifier
    And shorter relation guidance does not establish real learning improvement
    And its update conditions allow review when new verified evidence changes the source state
    And missing reusable knowledge keeps the original failure and costs without inventing an entry
    And confidence thresholds and complete counterevidence review remain unchanged
    And new record bodies state each supported fact once without a hard length limit
    And the index description can repeat one supported body fact for discovery
    And complete declarations retain independent named-type requirements and necessary source scope
    And runtime observations do not exempt retained type claims from their complete owning declarations
    And initial generation uses its complete parent-ref template without appending legacy quote-index or semantic-repair guidance
    And relational API knowledge connects a source-established factory or call site to its named return type and relevant declared member
    And concise generation does not authorize shortening a correct predecessor or dropping known conditions
    And both arms are told to run each required verification command separately without pipes or prefixes
    And unchanged exact native invocation checks reject filtered or prefixed upstream commands

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

  Scenario: A knowledge coverage account does not grant learning authority
    Given a complete frozen task and a proposed Memory record
    When a separate reviewer derives necessary facts and conditions within its knowledge scope from original evidence
    And it then compares those requirements and every actual claim with the complete record
    Then each selected evidence position is validated against the original task
    And each claimed body witness must occur in the exact proposed record
    And normal body-position witnesses begin after frontmatter, so a description cannot cover missing body knowledge
    And a leading byte-order marker cannot turn a description-only change into a required body correction
    And a wholly absent scoped fact or relation has no body witness
    And an uncovered necessary condition keeps the account incomplete
    And a populated account is not evidence that all necessary conditions were found
    And original source, consistency, privacy and mutation reviews remain required

  Scenario: Automatic nominations do not invent storage obligations
    Given an automatic task with no explicit request to store knowledge
    When a reusable fact is nominated for Memory
    Then its coverage scope is optional unless an original request or predecessor establishes an obligation
    And a tool result cannot be used as an original user request
    And temporary instructions and no-remember restrictions remain subject to complete semantic review

  Scenario: A complete plan account includes a wholly omitted requested goal
    Given original user evidence requests knowledge that has no proposed or retained record
    When the separate coverage worker reviews the actual empty plan
    Then a mandatory plan account names the missing obligation with original user references
    And no record slot is required for an absent record
    But a valid empty obligation list does not prove that no user obligation exists

  Scenario: Source support cannot serve as a stored Memory location
    Given a named knowledge obligation has a matching original source observation
    And no proposed or retained Memory record covers that obligation
    When the coverage account claims that the source is its stored location
    Then the parent rejects the account
    And an actual record witness cannot substitute for independent semantic review

  Scenario: Partial plans fail before coverage worker transport
    Given the actual plan contains two candidate bodies
    When the caller supplies only one body for coverage review
    Then the review fails before the worker starts
    And deletion operations remain in the complete plan even without body targets

  Scenario: Interrupted coverage review retains all known costs
    Given a separate coverage worker ends before its parent records a receipt
    When retained learning costs are recovered
    Then the known usage is counted once by the worker ledger identity
    And incomplete settlement remains unknown
    And a conflicting completion copy is rejected

  Scenario: Independent coverage can correct a source-supported but incomplete body
    Given the source and body consistency reviews accept a candidate
    And its actual body omits an original-evidence-supported applicability condition
    When independent coverage confirms that named omission at the original thresholds
    Then the existing bounded repair slot can correct its body and matching description
    And a confirmed body omission requires changed body text
    And complete original and rejected-version questions receive fresh full review
    And mutation requires all source, permission, preservation, consistency and joint coverage gates
    And the initial hold, corrected plan, numeric decisions and all costs remain separate

  Scenario: A global complete answer cannot erase a named missing condition
    Given a current or prior rejected account names an uncovered or null-witness condition
    When the independent judge reviews the exact current complete plan
    Then the whole plan and every actual record are independently checked
    And every named missing item needs its own resolved decision
    And exact duplicates for one target share a decision that covers every bound occurrence
    But different predecessor revisions or scope identities remain separate questions
    And all necessary scores compose conservatively without an independence assumption

  Scenario: A complete-plan coverage proof cannot authorize a different subset
    Given independent candidates have a coverage proof bound to the complete plan
    When a proposed subset changes that actual plan
    Then the complete-plan proof does not authorize that subset
    And the parent holds it until there is a separate exact subset obligation proof
    And legacy explicitly bounded study wires retain their original protocol

  Scenario: Retention judgment costs survive later source or artifact failure
    Given an independent retained-record review has returned
    When a later source assertion or semantic-proof write fails
    Then its numeric usage is already owned by the original run
    And the main and sibling results are counted once by their actual invocation ownership
    And a cancelled predecessor cannot append those costs to a successor

  Scenario: Rejected complete coverage does not suppress independent error diagnosis
    Given a complete retained coverage response fails account binding
    And its original task, candidate plan and source revisions remain unchanged
    When independent source or body review confirms a repairable hold
    Then the existing single plan repair can change the held knowledge
    And the rejected account remains invalid without prior proof authority
    And every fresh source, coverage, body and mutation gate must pass before writing

  Scenario: A bad coverage account alone cannot trigger another judgment
    Given a complete rejected coverage account
    And each claim requires an explicit conditions array, including an empty array when no material condition is identified
    And independent source and body review find no repairable error
    When the Memory attempt settles
    Then it remains proposed without writing or retrying the account
    And unsafe, incomplete, cancelled or unavailable responses cannot continue diagnosis

  Scenario: Failed learning keeps its exact rejected coverage questions for backfill
    Given a source-bound rejected Memory plan with a named omission
    When a later task receives feedback from its actual receipt and retained review artifacts
    Then every original question, occurrence and numeric classification is retained
    And complete plan obligations and claim-condition relationships retain their historical versions
    And an exact duplicate prior account may reference only an earlier fully validated version
    And the unchanged feedback byte limit rejects excess work without dropping knowledge relationships
    And the historical diagnosis is not source evidence, a required answer or mutation authority
    And altered, ambiguous or unavailable new diagnostics stop safely
    And fresh source and every complete semantic gate remain required

  Scenario: Local Memory coverage does not inherit another record's omitted goal
    Given one candidate preserves its bounded knowledge and another requested goal is missing
    When the parent selects the scoped-record question contract
    Then the candidate and retained-record questions use their own knowledge scope
    And the unchanged complete-plan question still holds the incomplete plan
    And all source, privacy, permission, preservation and numeric gates remain required
    And historical reviews without that contract retain their exact original questions
    And unknown or changed question contracts cannot authenticate replay feedback

  Scenario: Explicit Memory maintenance runs while automatic learning is off
    Given an ordinary source edit with automatic learning disabled
    And an existing stale Memory and an unrelated manual Harness rule
    When the user invokes /memory 整理记忆
    Then the parent collects current source before complete correction review
    And approved knowledge is written identically to both safe Memory roots
    And low-confidence review preserves the old Memory without writing
    And the manual Harness rule stays unchanged in both cases
    And controlled judgments establish command wiring, not learning benefit

  Scenario: Diagnostic labels do not establish unexecuted work
    Given a diagnostic prints an action label without executing that action
    And a separate failing reproducer executes additional work
    When initial Memory generation or correction receives the complete evidence
    Then each observation keeps its own executed operations and ordering scope
    And the original setup order and unreleased work remain explicit where needed
    And a description change does not establish that unchanged knowledge was corrected
    And every semantic gate remains required before any write

  Scenario: Explicit initialization does not forge automatic Harness ownership
    Given an empty knowledge corpus and an unrelated manual Harness fixture
    When a real Memory command completes approved source-grounded creation
    And a separate original-user policy task starts automatic consolidation
    Then the parent creates the new rule's consolidation ownership and revision
    And native tool calls prove both its block and its unrelated allowance
    And the manual rule remains unchanged
    And held Memory starts no dependent policy task
    And the source backlog is verified empty before that policy task starts
    And an earlier held attempt and all its costs remain after successful correction

  Scenario: Same-session initialization does not double count source-task usage
    Given a complete original native session and its exact digest
    When an explicit Memory command continues that session
    Then the original evidence remains available and only new output is counted
    And all initialization costs and time enter the experiment total
    And changed prefixes fail without converting unbound reported costs to zero

  Scenario: Direct Memory command source proof keeps its native origin
    Given the owner retained the actual Memory invocation and complete native session
    When the study reconstructs the command's learning evidence
    Then it uses the production task projection and current-source extension validator
    And it binds the native receipt, generation ledger and source collector ledger
    And changed arguments, prefixes, source reads or ledger usage fail verification
    And provenance alone approves neither initialization nor semantic learning
    And completed replay ownership remains a separate proof path
    And the launcher binds its actual container, CLI arguments and Pi version
    And bounded regular-file reads reject links, replacement and path aliases
    And complete source bytes and modes remain unchanged across the command
    And malformed or ambiguous generation ledgers stop command reconstruction

  Scenario: Direct command audit binds stored knowledge before semantic review
    Given a complete direct command and its approved initial CREATE plan
    When the independent audit prepares its source-safety and knowledge questions
    Then actual entry bytes and revisions match the plan and receipt-owned history
    And each safe entry has the same bytes in both Memory roots
    And missing knowledge, foreign history or changed counts stop before the SDK
    And nonempty prior knowledge also stops before the SDK
    And original and correction ledgers retain their distinct usage
    And both semantic questions retain their individual and joint gates

  Scenario: Later learning retains every original batch receipt
    Given a real Memory command has saved its receipt
    When source backfill and a separate automatic policy task finish
    Then each batch receipt remains in its own directory
    And the flat receipt remains a compatibility view of the latest result
    And cost collection collapses only equal views of the same batch
    And conflicting views or missing historical usage never become zero cost

  Scenario: Cancellation during receipt storage keeps one terminal batch state
    Given the parent is saving a learning receipt
    When shutdown cancels the pipeline during that write
    Then the canonical batch and compatibility receipt contain the cancelled state
    And the original recovery reference stays available
    And no completed learning result is reported

  Scenario: Command initialization closure is processing rather than learning
    Given the source task has produced reviewed command Memory
    When one actual source backfill closes its pending range
    Then the original Memory corpus and all physical surface revisions stay unchanged
    And the original source session and exact receipt digest bind the acknowledgement
    And all earlier receipts and costs remain available
    And an initialization exception keeps its request counts and unknown usage

  Scenario: Correction receives distinct existing semantic observations
    Given a normal Memory CREATE held by separate coherence and source checks
    When the parent prepares its single semantic correction
    Then both controlled observations remain distinct without new judgment calls
    And bounded diagnostic truncation is explicit in the actual repair input
    And observations grant no new repair fields or mutation permission

  Scenario: Citation repair preserves source-supported applicability
    Given a rejected record has a material condition without a selected citation
    And the complete original source establishes that condition
    When the parent prepares the existing semantic correction
    Then repair guidance keeps the condition and adds the matching source citation
    And it checks for lost applicability limits before returning the patch
    And the final parent diagnostics permit source-supported omissions in admitted fields
    And missing citations alone never require removal of a supported condition
    And false or obsolete conditions remain correctable from original evidence
    And unresolved material scope keeps the correction pending under all original gates

  Scenario: Initial knowledge catalog correction preserves the ordered body
    Given a new project proposal contains exact source units and cited usage conditions
    And one original-source citation exceeds the unchanged 2000-character limit
    When the existing structural correction repairs that citation
    Then the parent retains the typed citation failure and selects citation-only correction
    And the worker receives the invalid source-catalog position and the original extraction bound
    And the worker replaces only the same-length ordered source catalog
    And every original body unit, description, name and privacy classification remains unchanged
    And added or removed catalog positions and body replacements are rejected
    And current-source materialization and all semantic and transaction gates still apply
    And the rejected original proposal and every correction cost remain retained

  Scenario: An opted-in Sol planner uses Responses JSON mode in isolation
    Given the operator selects gpt-6.1-sol with the Responses API
    And the isolated learning worker has no active tools and JSON output is enabled
    When the native Pi 1.3 worker prepares its request
    Then text.format requests a JSON object without changing the task or reasoning
    And existing caller output constraints and other text settings stay unchanged
    And unknown model APIs and workers with tools receive no added format
    And complete parent source, citation, knowledge and mutation reviews still apply
    And native loopback transport does not establish real-model learning benefit

  Scenario: Citation-only correction cannot resample a valid coverage hold
    Given complete bound coverage accounts and a held independent coverage judgment
    And the repair worker receives the parent-bound requirement for a real source-supported knowledge change or empty refusal
    When the repair changes only selected citations for unchanged knowledge and original evidence
    Then the original coverage hold and returned response and usage remain retained
    And no fresh coverage judgment or Memory write occurs
    And another held source or counterevidence check cannot unlock a second coverage draw
    But when coverage itself passed, an independently held source claim may still receive an evidence-only correction
    And changed knowledge requires fresh complete source, body and coverage review

  Scenario: Each counter judgment has the scope of its transmitted indexed window
    Given normal Memory counterreview partitions complete original evidence into indexed windows
    When the parent sends a window with its complete cited support and supplied source-comparison context
    Then its answer criteria judge that window rather than claiming unseen whole-task chronology
    And all eligible original entries remain unchanged across the ordered complete window set
    And an independent hold in the last window still holds the complete plan at the original gates
    And the separate whole-plan coverage question keeps its complete original scope
    And explicitly bounded historical question bytes remain unchanged


  Scenario: Failed-task knowledge retains independent applicable contract relationships
    Given a completed failed task includes inspected contracts and its observed limitation
    When the existing incremental planner receives the unchanged original dossier
    Then its generation policy deduplicates repeated statements without compressing independent applicable facts
    And the failed-task pitfall does not displace material inspected contract relationships merely because source is available
    And each reusable relationship keeps its evidenced dependencies, ownership and conditions
    And it need not invent facts or copy an unrelated symbol inventory
    And project proposals use knowledge units while personal preferences use prose content and evidence
    And the parent remains compatible with legacy complete project proposals
    And source restrictions, citation bounds and every semantic gate remain unchanged
    And a delivered generation contract alone does not establish model compliance or learning benefit

  Scenario: Observed declaration syntax exposes related owners without generating knowledge
    Given an original successful declaration-file read with its unique preceding tool call
    When the parent projects the same frozen evidence for the existing Memory generator
    Then the data view shows direct outer return annotations and observed named type members with original source references
    And callback return annotations do not become the outer function's returned object
    And ambiguous, malformed or oversized syntax adds no guessed relationship
    And original evidence, source order, citation bounds and every learning gate remain unchanged
