Feature: Failed or aborted planner output cannot become a learning candidate
  Scenario: A failed assistant includes a valid JSON plan
    Given a planner reply contains a syntactically valid Memory, Harness or AGENTS.md plan
    And its terminal reason is error or aborted even though the CLI exits successfully
    When the parent extracts the child plan
    Then no plan is accepted from that reply
    And the failure is classified as model failure or cancellation
    And no repair, semantic judgment or application uses its partial text

  Scenario: A planner fails after emitting an earlier plan
    Given a structured plan was emitted before a terminal failure
    When the complete child transcript is inspected
    Then the earlier plan cannot escape the failed terminal state

  Scenario: The worker explicitly recovers with a successful fresh reply
    Given a failed reply is followed by a successfully completed reply
    When the successful reply supplies a valid bound plan
    Then only the recovered reply can be accepted
    And legacy structured-plan output without terminal messages remains supported

  Scenario: Retry bookkeeping follows an aborted reply
    Given a model error is followed by an aborted reply
    And Pi emits a successful retry bookkeeping event
    When no successful fresh assistant reply follows
    Then the planner remains cancelled and does not request repair

  Scenario: Failed usage is unavailable in a compatible receipt
    Given a failed attempt has no authoritative usage
    When the pipeline receipt is built or a legacy receipt is displayed
    Then missing usage and cost are unavailable rather than zero or free
    And completed attempts remain identifiable as known subtotals

  Scenario: An empty recovery cannot restore a failed-state legacy plan
    Given a legacy structured plan was emitted while the child was failed
    When a successful fresh assistant reply contains no plan
    Then the failed-state plan is not accepted

  Scenario: Incomplete planner cost keeps its known prefix without claiming a full receipt
    Given a planner completed paid replies before an error or an incomplete usage record
    When the parent records the attempt
    Then the numeric ledger retains all known usage and cost
    And the receipt does not mark the attempt usage as complete
    And only an actual matching persistent receipt excludes a ledger from additional known costs

  Scenario: JSON encoding preserves the sensitive material decision
    Given source documentation has an authorization heading followed by a code block
    When the source is encoded in a frozen JSON dossier
    Then escaped line breaks do not invent a credential
    And actual credentials in decoded values or keys remain refused

  Scenario: One citation repair sees simultaneous count and coordinate failures
    Given a plan has an out of range location and another candidate has nine citations
    When the parent prepares the existing single structural repair
    Then it reports both failures within the unchanged diagnostic bound
    And exact citation extraction and the eight item acceptance bound remain required

  Scenario: Missing source paths do not erase independently verified observations
    Given a maintenance audit observed current source and a nonexistent allowed path
    When the parent independently verifies both with the original scope
    Then the missing path contributes no fact or citation
    And verified current source remains available
    And sensitive, out of scope or changed paths still fail the audit

  Scenario: Source read exhaustion preserves evidence and stops excess work
    Given a maintenance worker uses its eighteen admitted reads
    When it requests its next OpenAI completions response with no active tools
    Then the wire request explicitly disables tool calls and retains observed results
    And any excess in flight read is recorded and aborts the invalid audit

  Scenario: Assistant inference remains context during maintenance
    Given a frozen task includes assistant inference and actual source observations
    When the planner receives the complete evidence projection
    Then each original index explicitly labels its citation eligibility
    And assistant text remains present but cannot establish remembered knowledge

  Scenario: Structured-plan repair retains its actual selected scope
    Given an existing-record plan has invalid citations and is not damaged output
    When the parent requests the single structural repair
    Then it does not announce an empty selected scope
    And damaged-output recovery alone receives private new-proposal instructions

  Scenario: Alternate positional selector notes never grant phase routing
    Given a bounded selector response uses selectedIndexes and surface notes without required flags
    When its positions and every present field pass the repair admission checks
    Then the original decision remains rejected and one independent correction is requested
    And only a complete corrected schema can route learning
    And both calls and the original failure remain recorded

  Scenario: A selector omits only its terminal object brace
    Given the bounded response would fully validate with one terminal brace
    When the parent admits the existing independent correction
    Then the diagnostic reconstruction is never accepted as the decision
    And a new complete valid response is required
    And stale identity, invalid fields and other damaged output remain refused

  Scenario: Explicit existing-Memory maintenance receives only a plan prefix
    Given selected existing Memory and complete original evidence are parent-bound
    And a successfully terminated response contains incomplete JSON and no established plan
    When source and Memory bindings remain unchanged
    Then one independent complete replan may use the same full dossier and selected scope
    And the prefix never authorizes an operation or becomes a repaired plan
    And the first failure, its artifacts and both costs remain recorded
    And a second incomplete response stops without another replan
    And ordinary learning, model errors, timeouts and output limits never use this path

  Scenario: A rejected existing operation mislabels parent-owned privacy
    Given the frozen inventory owns each selected Memory classification
    And a rejected plan contains both an invalid citation and a conflicting classification
    When the single structural correction receives complete frozen context
    Then it receives both errors and the exact selected classification table
    And it may correct only existing operation classifications to that table
    And new proposal privacy and semantic amendment privacy remain immutable
    And final parent inventory, citation and semantic gates still apply

  Scenario: A rejected deletion is reconsidered without erasing the existing record
    Given an unvalidated deletion in a structurally rejected maintenance plan
    And the frozen parent inventory owns the selected record and its classification
    When the single structural correction proposes a complete cited rewrite of that exact record
    Then the model's unvalidated deletion does not force another deletion
    And all original names and parent-owned classifications remain exact
    And deletion-only fields are forbidden on the rewrite
    And dropping records, introducing targets and rewrite-to-delete escalation remain refused
    And semantic amendments cannot use this transition
    And final source, citation, predecessor preservation and semantic gates still apply before any write

  Scenario: Reconsidering a deletion cannot bypass a missing current preservation review
    Given a structural correction converted an unvalidated deletion to a selected rewrite
    When Memory review is disabled or its complete current evidence and predecessor proof is missing
    Then no reconsidered Memory transaction is applied
    And partial evidence windows and changed evidence or predecessor digests are refused
    And the bootstrap history, rejected deletion, correction and costs remain retained

  Scenario: Source collection stops after its complete read budget without claiming worker success
    Given eighteen unique successful scoped reads and their actual complete tool results
    When the trusted collector binds their delivered prefix and aborts itself before another provider call
    Then the parent independently rechecks the nonce, prefix, calls, results, source revisions and abort terminal event
    And verified source observations may proceed while the worker remains recorded as failed or cancelled
    And partial delivery, duplicate IDs, refused or excess reads, other failures and external cancellation remain held
    And known usage remains counted with interrupted or missing usage marked unknown
    And the complete source citation, semantic and mutation gates remain required

  Scenario: Pi standard AbortError spelling preserves controlled collection proof
    Given eighteen complete source read calls and results bound to the parent scope and nonce
    When Pi emits its standard aborted terminal with or without the final period
    Then a zero-usage empty terminal and aborted signal are still required
    And an unrelated model or transport error cannot admit the source prefix

  Scenario: Stop source collection at a complete near-budget turn
    Given a hard cap of eighteen source reads and a fully delivered sixteen-read prefix
    When that trusted source turn finishes without pending reads
    Then the collector stops before another parallel batch can overshoot
    And every delivered read is independently revalidated
    And a nineteenth read remains a failure with no admitted source prefix

  Scenario: Node and Bun collectors use actual standard abort terminals
    Given the same complete source prefix under actual Node and Bun Pi processes
    When their runtimes emit distinct standard AbortError messages
    Then the parent binds each exact known terminal without accepting unrelated errors

  Scenario: A scoped missing file does not invalidate independently verified source
    Given a complete prefix with a parent-controlled missing-path tool error and verified source reads
    When the parent rechecks the missing path and every actual source revision
    Then the missing path supplies no fact or absence claim
    And the independently verified source prefix can enter subsequent learning gates
    But a scope refusal, changed missing path or excess read still fails

  Scenario: Memory positional aliases admit one fresh selection but no authority
    Given a bounded rejected selector using memoryEntries and empty other-stage arrays
    When its known unique positions and present fields are structurally valid
    Then one independent complete selection may run from unchanged original evidence
    And the alias response never grants routing or supplies default flags
    And nonempty other-stage arrays, stale identity and duplicate positions remain rejected

  Scenario: Unknown selector schema receives at most one independent decision
    Given a bounded single JSON selector reply with no authoritative identity and valid present known fields
    When the reply does not match the required selector schema
    Then it is retained as failed and may trigger one fresh decision from unchanged original evidence
    And its unknown aliases are neither interpreted nor repeated to the correction worker
    And the fresh answer must pass the complete original selection protocol
    And identity conflicts, sensitive output and invalid present known fields remain refused

  Scenario: A verified selector gateway constrains the decision schema on the wire
    Given a frozen metadata-only selector and an explicitly enabled structured-output gateway
    And the retained failures include renamed fields and missing phase decisions
    When the isolated no-tool selector prepares its provider request
    Then the request requires selectedIndices, memory, harness, agents and reason with their exact types
    And caller constraints and parent identity, filename, phase and semantic validation remain authoritative
    And a gateway without the explicit capability opt-in keeps its existing output behavior

  Scenario: Memory workers constrain plan and amendment structure without choosing knowledge
    Given a verified strict-output gateway and the retained Memory failures with missing evidence or changed operation kinds
    When an incremental planner or repair worker prepares a no-tool request
    Then its parent-selected schema requires the matching delta or candidate-bound amendment envelope
    And every emitted candidate requires non-empty evidence with a supported citation form
    And references remain positions chosen by the model and extracted from the frozen snapshot by the parent
    And schema conformance does not bypass intent, identity, source, semantic, privacy, preservation or rollback checks

  Scenario: Private maintenance replay proves the admitted wire constraint without leaking content
    Given isolated explicit structured-output opt-in and unchanged private-review consent
    When the native maintenance command sends learning requests through its bounded proxy
    Then the report records only controlled format types, known stage schema names and a strict boolean
    And arbitrary schema bodies, names and private messages never enter wire metadata
    And the original project, Memory and user configuration remain unchanged

  Scenario: The output citation domain is bound to all eligible frozen source positions
    Given a retained real delta and repair repeatedly citing old Memory readbacks
    When the parent prepares the isolated strict Memory request
    Then every selectable reference label belongs to the complete eligible original source catalog
    And legacy citation indexes exclude assistant and Memory-reference entries
    And all context and source text remain unchanged and available for review
    And an oversized or invalid catalog fails locally rather than being trimmed or downgraded
    And positional membership does not establish truth, preservation or mutation authority

  Scenario: Repeated complete predecessor bodies use lossless in-state references
    Given a complete predecessor body repeated verbatim in an original review text block
    When a preservation review encodes its bounded request
    Then the original evidence remains byte-identical and complete
    And only the duplicate predecessor content becomes a hashed UTF-16 reference to that same state
    And unmatched or partial bodies remain inline and oversized requests remain refused
    And every affected question requires reading the complete predecessor without granting truth or authority
    And later corrections still prevent atomic approval

  Scenario: A current-bound positional selector alias can request one fresh decision
    Given a rejected selector uses selectedEntries and rationale with the exact current digest
    When every supplied field and index passes local repair-admission checks
    Then retain the original failed attempt and cost
    And allow one independent answer under the unchanged selector schema
    And never convert alias fields or supplied surfaces into a routing decision
    And reject stale identity, invalid indexes, malformed fields and a second invalid answer

  Scenario: Citation rejection must not lock an unvalidated deletion into a sparse amendment
    Given a rejected mixed Memory plan has invalid citations and an unvalidated deletion
    And complete original-source and predecessor-preservation review is enabled
    When the existing single structural correction slot runs
    Then admit candidate-bound citation amendments and same-name delete-to-rewrite replacements
    And retain every unaffected candidate without regenerating the full plan
    And permit only the already supported delete-to-rewrite reconsideration
    And preserve selected names, parent privacy and all subsequent validation gates

  Scenario: Empty provider tool delimiters do not silently end a manual Memory request
    Given a successful planner transport returns only empty tool delimiter tags
    When no plan, tool action or mutation intent can be recovered
    Then use the existing single structural correction slot for a frozen scoped answer
    And retain the first failure and both costs
    And preserve parent inventory privacy and complete source validation
    And treat new proposals as private and reject a second invalid answer
