Feature: Consolidate artifact validator
  Machine-check G2/G3/G4/G7 planning artifacts and privacy so
  /memory "Consolidate memory now" cannot claim done on cosmetic-only runs.

  Background:
    Given a complete Harness private memory directory and sanitized project .memory directory
    And planning artifacts inventory, cluster map, and staleness table

  # --- cluster coverage (G2) ---

  Scenario: Cluster map covers every inventory file exactly once
    Given inventory lists project_a.md and project_b.md
    And cluster map places each in a theme cluster
    When I run the cluster coverage check
    Then the check passes

  Scenario: Cluster map missing an inventory file fails
    Given inventory lists project_a.md and project_b.md
    And cluster map only lists project_a.md
    When I run the cluster coverage check
    Then the check fails with "missing from cluster"

  Scenario: Cluster map with duplicate membership fails
    Given inventory lists project_a.md
    And cluster map lists project_a.md in two clusters
    When I run the cluster coverage check
    Then the check fails with "duplicate"

  Scenario: Cluster map with unknown file not in inventory fails
    Given inventory lists project_a.md
    And cluster map lists project_a.md and orphan.md
    When I run the cluster coverage check
    Then the check fails with "not in inventory"

  # --- staleness coverage (G3) ---

  Scenario: Staleness table scores every inventory file
    Given inventory lists project_a.md and feedback_b.md
    And staleness assigns KEEP and SUPERSEDED respectively
    When I run the staleness coverage check
    Then the check passes

  Scenario: Staleness missing a file fails
    Given inventory lists project_a.md and project_b.md
    And staleness only scores project_a.md KEEP
    When I run the staleness coverage check
    Then the check fails with "missing from staleness"

  Scenario: Invalid staleness verdict fails
    Given inventory lists project_a.md
    And staleness scores project_a.md as MAYBE
    When I run the staleness coverage check
    Then the check fails with "invalid verdict"

  # --- report ground-truth paths (G4/G7) ---

  Scenario: Report with path arrow rows passes when project files exist
    Given inventory lists project_deploy.md
    And report contains "src/deploy.ts → found"
    When I run the report ground-truth check
    Then the check passes

  Scenario: Report without path rows fails when project_* present
    Given inventory lists project_deploy.md
    And report has no path arrow lines and no N/A ground-truth
    When I run the report ground-truth check
    Then the check fails with "path"

  Scenario: Report may use N/A when no repo
    Given inventory lists project_deploy.md
    And report contains "Ground truth: N/A (no repo)"
    When I run the report ground-truth check
    Then the check passes

  Scenario: Report without path rows passes when only feedback_* inventory
    Given inventory lists feedback_pref.md only
    And report has no path arrow lines
    When I run the report ground-truth check
    Then the check passes

  # --- two-root privacy and mirror contract ---

  Scenario: Safe memory is byte-identical in both roots
    Given a safe filename exists in Harness private and project .memory
    When I run the privacy check
    Then both copies must have identical bytes

  Scenario: Harness-only memory never appears in project shared
    Given the private index marks a filename as harness only
    When I run the privacy check
    Then that filename must be absent from project .memory

  Scenario: Memory roots must be distinct
    Given the private and project-shared roots resolve to one canonical directory
    When I run the privacy check
    Then validation fails with a distinct roots diagnostic

  Scenario: Private-only memory validates without a project mirror
    Given a complete Harness private memory directory for a non-Git scope
    And no public memory root is supplied
    When I run final plan, receipt, and privacy validation
    Then the private index, files, classifications, and receipt hashes are validated
    And validation does not require a public mirror

  # --- full gate ---

  Scenario: Full validate passes only when all selected checks pass
    Given valid inventory, cluster, staleness, report, and two-root privacy layout
    When I run the full validator
    Then exit code is 0

  Scenario: Full validate fails closed on any single failure
    Given valid artifacts except cluster missing one file
    When I run the full validator
    Then exit code is 1

  Scenario: Automatic deletion must prove where knowledge survives
    Given an automatic plan proposes deleting a contradicted, superseded, or subsumed memory
    When preservedIn names an existing repository file or a memory rewritten in the same transaction
    Then validation accepts the deletion
    But deletion without a mechanically verifiable preservation target is rejected

  Scenario: Manual deletion must prove where knowledge survives
    Given a manual plan proposes deleting a contradicted, superseded, or subsumed memory
    When preservedIn names an existing repository file or a memory rewritten in the same transaction
    Then validation accepts the deletion
    But deletion without a mechanically verifiable preservation target is rejected
    And KEEP, DORMANT, OPS-ONLY, and ONE-SHOT memories cannot be deleted

  Scenario: Bulk external memory deletion is blocked
    Given a generated shell call deletes the project memory directory, its index, or several memory files
    When the built-in Harness evaluates the call
    Then it blocks the call and directs the user to parent-owned consolidation
    But unrelated project cleanup remains allowed

  # --- structured run binding and strict artifacts ---

  Scenario: Inventory rejects duplicate and path-qualified entries
    Given an inventory contains duplicate names or a path component
    When I run the structured validator
    Then validation fails with an artifact identity diagnostic

  Scenario: Index names are recognized case-insensitively
    Given an inventory contains MEMORY.md in mixed case
    When I run the structured validator
    Then the index is excluded from non-index coverage

  Scenario: Legacy underscore verdicts are rejected
    Given staleness contains OPS_ONLY instead of OPS-ONLY
    When I run the structured validator
    Then validation fails with an invalid verdict diagnostic

  Scenario: A foreign or stale receipt is rejected
    Given a receipt has a different run id, scope digest, or artifact hash
    When the parent verifies the receipt
    Then validation fails before completion is reported

  Scenario: Memory roots reject symlinked files
    Given a memory root or Markdown child is a symlink
    When I run the privacy check
    Then validation fails with a symlink diagnostic

  Scenario: Ground truth is checked per selected memory
    Given two selected project memories with distinct repository claims
    And only one claim has a valid repository-relative observation
    When I run the structured validator
    Then validation fails for the missing per-memory grounding row

  Scenario: Ground truth paths stay inside the repository
    Given a grounding record points outside the repository root
    When I run the structured validator
    Then validation fails with a repository containment diagnostic

  Scenario: A valid receipt binds the selected scope and final generation
    Given a schema-valid plan and post-apply receipt match the run id, scope digest, selected files, and final hashes
    When the parent verifies the receipt
    Then validation passes and emits a structured success receipt

  Scenario: Receipt validation requires a phase and phase-specific hashes
    Given a receipt has valid identity and final hashes but no phase
    When I run post receipt validation
    Then validation fails with a missing phase diagnostic

  Scenario: Post receipt binds the exact plan artifact bytes
    Given a post receipt records the SHA-256 digest of the exact plan JSON bytes
    When the plan file is replaced with another schema-valid plan
    Then post receipt validation fails with a plan artifact binding diagnostic

  Scenario: Plan scope key is not an alias for scope digest
    Given a plan contains distinct canonical scopeKey and scopeDigest values
    When I run the structured validator
    Then validation passes when both values match the parent-supplied run
    And validation fails when either canonical value is changed

  Scenario: Canonical project scope follows realpath aliases
    Given /var/tmp and /private/var/tmp refer to the same directory
    When memory paths resolve each spelling
    Then both paths have the same canonical project cwd and scope key

  Scenario: Memory loading bounds bytes before allocating file content
    Given a valid memory file is larger than the configured file character limit
    When the memory loader reads it
    Then it reads only a bounded prefix before decoding
    And it preserves the configured truncation marker

  Scenario: Memory loading rejects a child replaced by a symlink
    Given a valid memory file is replaced by a symlink during loading
    When the memory loader opens the file
    Then it skips the replaced file without exposing the symlink target

  Scenario: Memory config writes reject symlink roots and targets
    Given the configured agent directory or memory config target is a symlink
    When memory config is written
    Then the write fails closed without writing outside the configured agent directory
    And an existing symlink target remains unchanged

  Scenario: Receipt path is bound to the plan run directory
    Given a valid post receipt has the expected filename in another directory
    When I run post receipt validation
    Then validation fails with an exact receipt path diagnostic

  Scenario: Post receipt source hashes bind when supplied by the transaction contract
    Given a post receipt includes source hashes from the parent snapshot
    When a source hash is changed in the receipt
    Then post receipt validation fails with a source hash binding diagnostic

  Scenario: Memory layer roots cannot be the same canonical directory
    Given two enabled memory layer roots resolve to one canonical directory
    When I run the privacy check
    Then validation fails with a distinct roots diagnostic

  Scenario: Validator rejects oversized memory roots before reading bytes
    Given a memory root exceeds the validator file count or byte bounds
    When I run the privacy check
    Then validation fails with a memory bounds diagnostic

  Scenario: Grounding found observations must point to existing repository files
    Given a project memory grounding row marks a nonexistent path as found
    When I run the structured validator
    Then validation fails with a grounding existence diagnostic

  Scenario: Operations cannot change inventory classification
    Given an operation classification disagrees with the inventory classification
    When I run the structured validator
    Then validation fails with a classification binding diagnostic

  Scenario: Selected scope must match the parent expectation
    Given a plan selected scope differs from the parent-supplied selected scope
    When I run the structured validator
    Then validation fails with a selected scope binding diagnostic

  Scenario: New memory proposals have a separately bounded scope
    Given selected is an empty parent-owned scope and newMemories contains one proposal
    And the proposal cites a user entry in the immutable snapshot
    When I run the structured validator with that snapshot
    Then plan validation passes without adding the new name to selected or inventory
    And the validator reports one new memory proposal

  Scenario: New memory names cannot overlap selected names
    Given selected contains project_example.md
    And newMemories proposes project_example.md again
    When I run the structured validator with the immutable snapshot
    Then validation fails with a new memory scope diagnostic

  Scenario: New memory evidence rejects assistant-only context
    Given newMemories cites an assistant snapshot entry
    When I run the structured validator with the immutable snapshot
    Then validation fails with a context evidence diagnostic

  Scenario: New memory evidence rejects stale or altered snapshots
    Given newMemories cites a quote that exists in the original snapshot
    When the snapshot bytes change before validation
    Then validation fails with a snapshot digest or evidence diagnostic

  Scenario: New memory content and evidence reject secrets
    Given newMemories contains an API token in its content or evidence quote
    When I run the structured validator with the immutable snapshot
    Then validation fails with a sensitive material diagnostic

  Scenario: Post receipt binds created new memory names
    Given a valid plan creates a new memory
    When the post receipt omits or changes its created names
    Then receipt validation fails with a created scope binding diagnostic
