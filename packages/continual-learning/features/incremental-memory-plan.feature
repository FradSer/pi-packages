Feature: Expand an incremental Memory delta into the full parent-owned plan
  Incremental planners describe only proposed changes. The parent derives the
  exhaustive validation shape from the immutable consolidation run and exact
  selected Memory names before existing validation or mutation can occur.

  Scenario: Parent expands a valid delta without model-authored unchanged state
    Given a ConsolidationRun whose private MEMORY.md classifies one safe and one private selected Memory
    And a delta plan with matching identity fields, one selected rewrite, and one new Memory proposal
    When the parent expands the delta for the exact selected names
    Then the full plan contains the exact selected inventory with parent-derived classifications
    And every selected item belongs to one deterministic cluster
    And unchanged items receive KEEP staleness, UNVERIFIABLE grounding, and an unchanged report
    And the expanded plan is compatible with the existing validator and applyConsolidationPlan

  Scenario: Repository observations are accepted only after parent validation
    Given a selected project Memory delta operation cites bounded repository observations
    When every cited path is repository-relative, has an allowed status, and a found path is an existing file
    Then the full plan uses those observations for that Memory's grounding record
    But an invalid, escaping, or nonexistent found observation is rejected

  Scenario: Delta identity and scope fail closed
    Given a delta plan has a foreign run identity, an operation outside selected, or a duplicate selected or operation name
    When the parent attempts expansion
    Then expansion is rejected before producing a full plan

  Scenario: Semantic correction selects a short reference under a frozen proposal binding
    Given the complete original proposal digest and exact candidate references captured before a repair worker
    When the worker explicitly selects a candidateRef with the exact run and snapshot identity
    Then the parent binds that reference to the original full candidate digest
    And changed proposals, snapshots, mixed selectors and duplicate targets are rejected
    And citation-only repairs cannot use candidateRef
    And a malformed historical candidateId remains rejected
    And complete source, privacy, protected-field and semantic checks remain required

  Scenario: Parent classifications cannot be overridden
    Given private MEMORY.md classifies a selected Memory as private
    When the delta operation labels it safe or uses an invalid classification
    Then expansion is rejected

  Scenario: Incremental operations cannot create an already selected Memory
    Given the parent selected an existing Memory file
    When the delta operation uses the create kind for that file
    Then expansion is rejected
    And new knowledge remains expressible only through newMemories

  Scenario: Deletes require an allowed explicit verdict and verifiable preservation
    Given a delta operation deletes selected Memory
    When it omits an allowed CONTRADICTED, SUPERSEDED, or SUBSUMED verdict
    Then expansion is rejected
    And KEEP is derived for all operations that do not explicitly authorize deletion
    And preservation targets remain subject to the existing validator

  Scenario: Missing observations are checked against actual repository state
    Given a delta labels one existing repository path as missing
    When the TypeScript parent or Python validator validates the observation
    Then the contradictory observation is rejected
    And a genuinely absent contained path remains valid missing evidence

  Scenario: Repository aliases preserve canonical containment
    Given a repository parent directory is a symlink
    When its resolved target stays inside the repository
    Then regular-file observations through that alias remain valid
    But an alias resolving outside the repository is rejected

  Scenario: Semantic repair can distinguish current and earlier source observations
    Given uniquely paired successful earlier and bound later reads of the same supplied path
    When the semantic repair worker receives complete original evidence
    Then its generation guidance permits an optional source-cited temporal clarification
    And it must not infer dates, releases, runtime success, or original Memory purpose
    And stable facts and material conditions remain complete without copying the whole predecessor
    And user revocations, privacy, and temporary restrictions still govern
    And an uncertain verdict does not require changing an already correct body
    And every amendment still needs full fresh semantic review before any write

  Scenario: Semantic repair uses the original frontmatter shape
    Given a held candidate with complete frontmatter that omits an optional name field
    When the parent supplies a semantic correction example
    Then the example preserves every protected field and its absence
    And only a held description may change in that header
    And the parent still preserves the original header before full review
    And deletion reconsideration examples use the selected record header instead of inventing metadata

  Scenario: A validated semantic repair retains parent-owned causal provenance
    Given one actual repair worker invocation and its complete rejected plan
    When the parent constrains, materializes and validates the returned plan
    Then one receipt binds its native ledger, task input, identity, raw response and actual plan bytes
    And canonical plan digests remain distinct from serialized artifact byte digests
    And copied results, swapped ledgers and changed output cannot borrow another result's provenance
    And each invocation retains its immutable response while the generic response remains a latest view
    And publication cannot replace an artifact created concurrently
    And partial or unpriced usage remains recorded without invalidating a proved causal association
    And invalid or sensitive output keeps its existing rejection and hash-only handling
    And the receipt grants no semantic approval, Memory write authority or learning success

  Scenario: A held review does not require an invented factual correction
    Given a candidate-bound semantic correction with complete original evidence
    When the worker considers the held claims
    Then it first identifies a source-backed factual or citation gap
    And it preserves supported claims while correcting incomplete citations
    And it returns an empty amendment when no supported correction exists
    And the parent keeps an empty amendment failed with its usage
    And structural plan repair does not receive an incompatible amendment-only directive

  Scenario: Word apostrophes preserve an explicit API relationship
    Given selected source and an explicitly named wrapper-member relationship
    When visible prose uses word-internal possessives or contractions
    Then the existing relationship checks retain those identifiers
    And true quoted, fenced and blockquoted examples remain isolated
    And missing roles are not automatically selected or inferred

  Scenario: Declared roles do not imply runtime object inequality
    Given an observed declaration and a callable that can return itself
    When Memory generation or semantic correction explains the declaration
    Then the worker distinguishes the callable from its declared result type
    And type notation alone does not establish runtime identity or inequality
    And correction preserves still-valid knowledge without adding uncited reviewer cautions
    And complete source, body, permission and preservation review still applies

  Scenario: Keep a rejected structural plan before correction
    Given the parent rejects an original incremental Memory plan
    When the existing bounded structural correction runs
    Then the run artifact retains the exact rejected plan and its digest
    And a sensitive rejected output retains its digest without its plan
    And the original rejection, usage and all validation gates remain

  Scenario: Initial Memory planner preserves the configured network route
    Given the parent uses explicit HTTP and HTTPS proxy settings with Node environment-proxy opt-in
    When the parent starts its initial read-only Memory planner
    Then the planner retains that proxy route and local bypass list
    And unrelated credentials, arbitrary Node preloads and TLS-verification overrides are not inherited
    And source validation, semantic thresholds and retry budgets remain unchanged
