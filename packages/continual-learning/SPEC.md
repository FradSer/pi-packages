# Readable private Memory with a sanitized project mirror

## Problem Statement

Memory briefly moved to an opaque hash-based multi-layer model that no longer matched its established privacy semantics. Users need to recognize a project's private Memory directory on disk, while retaining the original behavior where the private Harness copy is complete and project `.memory/` contains only sanitized content safe to commit.

Harness configuration has a separate concern: it needs exactly three precedence layers and must not load obsolete global-personal or project `.pi/agent` files.

## Solution

Memory uses exactly two synchronized physical roots:

1. Complete Harness/private Memory at `~/.pi/agent/memory/<escaped-canonical-cwd>/`
2. Sanitized project-shared Memory at `<project>/.memory/`

The private directory, lock basename, and runs scope use the same flat ASCII identity derived from the canonical project path: NFKD normalization removes combining marks; separators, whitespace, and unsupported characters become dashes; repeated dashes collapse. Names longer than 240 bytes are rejected without truncation or hash fallback. This sanitizer is intentionally lossy: colliding canonical paths share Memory and operational scope. Content-integrity SHA-256 digests are unchanged. Safe files are byte-identical in both roots; private files exist only in the Harness root and are marked `(harness only)` in its index. No project-local private Memory directory is recognized. Pre-run normalization, consolidation transactions, rollback, validation, and receipts preserve this privacy split. Automatic and manual deletion require mechanically verified preservation, and generated shell bulk-deletion of Memory roots is blocked.

Harness retains exactly three configuration layers: user shared, project shared, and project personal.

## User Stories

1. As a user, I want a readable private Memory directory name, so that I can identify a project's state without decoding a hash.
2. As a user, I want the private Harness Memory root to contain all project Memory, so that runtime knowledge has one complete canonical source.
3. As a contributor, I want `.memory/` to contain only sanitized safe knowledge, so that it can be committed and shared.
4. As a user, I want project-shared edits imported when they are newer, so that Git-delivered knowledge reaches runtime Memory.
5. As a user, I want private edits mirrored outward only when safe, so that collaboration does not expose private information.
6. As a user, I want failed multi-root writes rolled back, so that the two roots never remain partially updated.
7. As a user, I want obsolete private-root layouts ignored, so only the flat canonical root can affect runtime Memory.
8. As a user, I want Memory indexes to match exact root contents and privacy markers.
9. As a user, I want Harness policy precedence to remain project personal over project shared over user shared.
10. As a user, I want obsolete global-personal and project `.pi/agent` Harness files ignored.

## Scenarios

```gherkin
Feature: Readable private Memory and sanitized project mirror

  Scenario: Private root and operational paths use one flat scope identity
    Given the canonical project path is /Users/FradSer/Developer/FradSer/cerberus
    When Memory paths are resolved
    Then the private root name is -Users-FradSer-Developer-FradSer-cerberus
    And the scope key, lock basename before .lock, and runs basename use that identity
    And locks live at memory/locks/<scopeKey>.lock separately from private directories
    And identities longer than 240 ASCII bytes are rejected

  Scenario: Private directory names cannot collide with lock storage
    Given projects foo and foo.lock with existing private Memory directories
    When both consolidation locks are acquired
    Then both locks coexist and releasing them preserves both private directories

  Scenario: Symlinked lock storage is rejected
    Given memory/locks is a symlink to an outside directory
    When a consolidation lock is acquired
    Then acquisition fails without writing outside Memory

  Scenario: Safe Memory is synchronized
    Given a Memory file is classified safe
    When consolidation applies it
    Then byte-identical copies exist in the private and project-shared roots

  Scenario: Private Memory stays private
    Given a Memory file is classified private
    When consolidation applies it
    Then it exists in the private root
    And it is absent from project .memory
    And the private index marks it harness only

  Scenario: Drift normalization chooses the newer side
    Given safe copies differ before planning
    When the consolidation run is created
    Then the newer mtime wins
    And equal mtimes prefer the private copy

  Scenario: First adoption imports project Memory
    Given project .memory exists and the private root does not
    When normalization runs
    Then project-shared files are copied into the private root

  Scenario: Transaction failure rolls back both roots
    Given one selected operation has modified both roots
    When a later operation fails
    Then both roots and indexes return to their predecessor bytes

  Scenario: Obsolete private roots are ignored
    Given old hash-only, hash-suffixed, or former-sanitizer Memory directories exist
    When Memory is loaded
    Then none of those obsolete roots is read, imported, renamed, or deleted
    And only the flat escaped canonical-path root participates at runtime

  Scenario: Harness resolves exactly three layers
    Given Harness declarations exist at user shared, project shared, and project personal
    When configuration loads
    Then project personal overrides project shared and user shared
    And obsolete global-personal and project .pi/agent Harness files are ignored
```

## Implementation Decisions

- `scopeKey` is the flat escaped canonical project path used for private Memory, locks, run directories, and plan binding.
- Validator CLI arguments bind leading-dash scope values with `--expected-scope-key=<scopeKey>`.
- Project `.memory/` is enabled only at the canonical Git worktree root.
- Strict valid Markdown basenames and `MEMORY.md` index exclusion apply to both roots.
- The pre-run parent normalizes drift, removes project-shared private leaks and orphans, and rebuilds both indexes.
- The child remains read-only. The parent owns validation, atomic writes, rollback, and receipts. AGENTS.md extraction persists an exact pre-apply recovery receipt before mutating Memory, Harness, or instructions. A later session validates and consumes an orphan pre receipt before new learning; a successful transaction retains it beside the verified post receipt.
- Safe create/rewrite writes both roots; private create/rewrite writes private and removes shared; delete removes both.
- Obsolete hash-only, hash-suffixed, whitespace-preserving, and former-sanitizer private roots are ignored. There is no discovery, import, approval, or compatibility read fallback; only the canonical flat `scopeKey` directory participates at runtime.
- Harness configuration remains a three-layer override system independent of Memory mirroring.

## Testing Decisions

- Path tests assert exact readable escaping and canonical/symlink convergence.
- Obsolete-root tests verify old layouts are neither read nor mutated, while current sanitizer collisions intentionally share the same private root and operational scope.
- Privacy tests verify mirror equality, private absence, exact indexes, limits, and symlink rejection.
- Transaction tests verify rollback of both roots and shared-write failures.
- Harness tests verify three-layer precedence, command targets, and ignored obsolete global-personal/project `.pi/agent` configuration.
- Full package pytest, strict TypeScript, package dry-run, installation check, and live Pi smoke are required.

## Context learning and executable constraints

- Automatic learning and default `/consolidate` operate on the newest completed Task Slice, not the complete session. A metadata-only selector chooses the minimum sufficient related Memory and produces one authoritative Learning Dossier; `/consolidate full` alone selects the full corpus.
- Incremental Memory, Harness, and AGENTS.md planners consume the same dossier and return deltas only. The parent expands deterministic validation/receipt sections and never falls back from failed selection to full exploration.
- With auto-memory enabled, a settled user task runs the parent-owned learning pipeline without requiring a command. Extension continuations do not independently retrigger it, overlapping completed tasks are coalesced, and headless execution waits for receipts.
- The existing-memory `selected` scope remains immutable. Bounded `newMemories` proposals cite user/tool snapshot messages and can create the first memory in an empty project. Creations obey the same privacy split and transactional rollback as existing edits.
- Memory and skill guidance supply context before generation. Harness policies explicitly check tool calls before execution, assistant output after generation, or actual file artifacts. Unsupported checks cannot report success.
- Learned policies require verifiable source quotes and executable positive/negative examples. Automatic learning cannot replace or disable user-owned constraints.
- Post-generation repair is bounded per user task and never claims already streamed output was withheld.

Acceptance contracts: `features/automatic-learning.feature`, `features/consolidate.feature`, `features/harness-consolidation.feature`, and `features/guardrails.feature`.

## Out of Scope

- A third physical Memory layer.
- Opaque hash names for steady-state Memory data.
- Automatic promotion of private Memory into shared Memory without safe classification.
- Loading obsolete global-personal or project `.pi/agent` Harness configuration.

## Further Notes

Memory and Harness both separate shared and personal concerns, but they do not use identical storage mechanics: Memory is a complete private corpus plus a sanitized mirror, whereas Harness is a precedence-based configuration stack.
