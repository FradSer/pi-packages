# Readable private Memory with a sanitized project mirror

## Problem Statement

Memory briefly moved to an opaque hash-based multi-layer model that no longer matched its established privacy semantics. Users need to recognize a project's private Memory directory on disk, while retaining the original behavior where the private Harness copy is complete and project `.memory/` contains only sanitized content safe to commit.

Harness configuration has a separate concern: it needs four user-owned
precedence layers (project personal, project shared, user scoped, and user
shared), plus package defaults, and must not load obsolete global-personal or
project `.pi/agent` files.

## Solution

Memory uses exactly two synchronized physical roots:

1. Complete Harness/private Memory at `~/.pi/agent/memory/<escaped-canonical-cwd>/`
2. Sanitized project-shared Memory at `<project>/.memory/`

The private directory, lock basename, and runs scope reuse Pi's flat session identity: remove the canonical path's leading separator, replace slashes and colons with dashes, and wrap it in double dashes. Unicode and existing punctuation remain intact. Names longer than 240 UTF-8 bytes are rejected without truncation or hash fallback. Separator replacement can produce collisions; the persisted identity is retained for compatibility. Content-integrity SHA-256 digests are unchanged. Safe files are byte-identical in both roots; private files exist only in the Harness root and are marked `(harness only)` in its index. No project-local private Memory directory is recognized. Pre-run normalization, consolidation transactions, rollback, validation, and receipts preserve this privacy split. Automatic and manual deletion require mechanically verified preservation, and generated shell bulk-deletion of Memory roots is blocked.

Harness retains four user-owned configuration layers: user shared, user scoped to
the project, project shared, and project personal, plus package defaults.

## Learning surface contract

Learning has three separate destinations with separate authority:

| Surface | Stores | Authority and proof |
| --- | --- | --- |
| Memory | Durable facts, references, and preferences | Untrusted context only; injection never enforces behavior or certifies a result |
| Harness | Evidence-backed executable checks and Bash execution conditions | Parent evaluator, exact selector, and bounded positive/negative cases; planner prose is not proof |
| Guidance | Scoped `skill`/`text` instructions and concise AGENTS.md pointers | Contextual direction only; delivery is not compliance evidence |

Automatic screening identifies plausible opportunities and may miss a lesson. A
screened-out task therefore cannot justify deletion or an absence claim. User and
tool-result evidence may ground a proposal; assistant claims, quoted instructions,
and repository prose that merely names a policy cannot. Human-owned manual,
built-in, personal, disabled, invalid, and legacy Harness declarations remain
protected. A single lesson may route to multiple surfaces only when each surface
has its own purpose and verification path.

Automatic learning state is bounded and fail-closed. Missing settings enable the
feature, while malformed, unknown, unsafe, or unreadable settings disable it and
surface a repair diagnostic. Skipped tasks may leave only a private scoped
reference in the backlog (4 MiB file, 4 KiB record); a full backlog rejects new
references rather than rotating away old evidence. Backlog inspection reports
status and scope diagnostics; it never drains or replays model calls. A
historical global cursor is consulted only for legacy records without
`scopeKey`; scoped records use their own cursor and remain pending regardless
of that global value. Full state checks validate settings, backlog
regular-file/size limits, scope binding, malformed references, and cursor
updates as one fail-closed state boundary.

## User Stories

1. As a user, I want a readable private Memory directory name, so that I can identify a project's state without decoding a hash.
2. As a user, I want the private Harness Memory root to contain all project Memory, so that runtime knowledge has one complete canonical source.
3. As a contributor, I want `.memory/` to contain only sanitized safe knowledge, so that it can be committed and shared.
4. As a user, I want project-shared edits imported when they are newer, so that Git-delivered knowledge reaches runtime Memory.
5. As a user, I want private edits mirrored outward only when safe, so that collaboration does not expose private information.
6. As a user, I want failed multi-root writes rolled back, so that the two roots never remain partially updated.
7. As a user, I want obsolete private-root layouts ignored, so only the flat canonical root can affect runtime Memory.
8. As a user, I want Memory indexes to match exact root contents and privacy markers.
9. As a user, I want Harness precedence to remain project personal over project shared over project-scoped user rules over user-shared rules.
10. As a user, I want obsolete global-personal and project `.pi/agent` Harness files ignored.

## Scenarios

```gherkin
Feature: Readable private Memory and sanitized project mirror

  Scenario: Private root and operational paths use one flat scope identity
    Given the canonical project path is /Users/FradSer/Developer/FradSer/cerberus
    When Memory paths are resolved
    Then the private root name is --Users-FradSer-Developer-FradSer-cerberus--
    And the scope key, lock basename before .lock, and runs basename use that identity
    And locks live at memory/locks/<scopeKey>.lock separately from private directories
    And identities longer than 240 UTF-8 bytes are rejected

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

  Scenario: Harness resolves four user-owned layers
    Given Harness declarations exist at user shared, user scoped, project shared, and project personal
    When configuration loads
    Then project personal overrides project shared, user scoped, and user shared
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
- Obsolete hash-only, hash-suffixed, and former-sanitizer private roots are ignored. Whitespace and Unicode in the current canonical flat `scopeKey` are preserved. There is no discovery, import, approval, or compatibility read fallback; only that directory participates at runtime.
- Harness configuration remains a four-layer user-owned override system independent of Memory mirroring.

## Testing Decisions

- Path tests assert exact readable escaping and canonical/symlink convergence.
- Obsolete-root tests verify old layouts are neither read nor mutated, while current sanitizer collisions intentionally share the same private root and operational scope.
- Privacy tests verify mirror equality, private absence, exact indexes, limits, and symlink rejection.
- Transaction tests verify rollback of both roots and shared-write failures.
- Harness tests verify four-layer precedence, command targets, and ignored obsolete global-personal/project `.pi/agent` configuration.
- Full package pytest, strict TypeScript, package dry-run, installation check, and live Pi smoke are required.

## Context learning and executable constraints

- Explicit full maintenance learns grounded new Memory even from an empty corpus. When its current context has no human/tool evidence, it may freeze one bounded recent same-project active context; receipts bind source session and digest. With neither evidence nor existing Memory it launches no workers and reports missing input.
- Automatic learning and default `/consolidate` operate on the newest completed Task Slice, not the complete session. A metadata-only selector chooses the minimum sufficient related Memory and produces one authoritative Learning Dossier; `/consolidate full` alone selects the full corpus.
- Explicit `/memory <request>` uses that request as primary immutable user evidence, with bounded previous-task context for reference. It runs validated Memory learning even when automatic learning is off, and the parent disables Harness and AGENTS.md phases for this invocation. The dossier marks the request entry so planners do not learn unrelated previous tasks.
- Incremental Memory, Harness, and AGENTS.md planners consume the same dossier and return deltas only. The parent expands deterministic validation/receipt sections and never falls back from failed selection to full exploration.
- With auto-memory enabled, a settled user task runs the parent-owned learning pipeline without requiring a command. Extension continuations do not independently retrigger it, overlapping completed tasks are coalesced, and headless execution waits for receipts.
- The existing-memory `selected` scope remains immutable. Bounded `newMemories` proposals cite user/tool snapshot messages and can create the first memory in an empty project. Creations obey the same privacy split and transactional rollback as existing edits.
- Memory and skill guidance supply context before generation. Harness policies explicitly check tool calls before execution, assistant output after generation, or actual file artifacts. Unsupported checks cannot report success.
- Learned policies require verifiable source quotes and executable positive/negative examples. Automatic learning cannot replace or disable user-owned constraints.
- Post-generation repair is bounded per user task and never claims already streamed output was withheld.

Acceptance contracts: `features/automatic-learning.feature`, `features/consolidate.feature`, `features/manual-memory-request.feature`, `features/command-memory-menu.feature`, `features/command-harness-menu.feature`, `features/harness-consolidation.feature`, and `features/guardrails.feature`.

## Out of Scope

- A third physical Memory layer.
- Opaque hash names for steady-state Memory data.
- Automatic promotion of private Memory into shared Memory without safe classification.
- Loading obsolete global-personal or project `.pi/agent` Harness configuration.

## Further Notes

Memory and Harness both separate shared and personal concerns, but they do not use identical storage mechanics: Memory is a complete private corpus plus a sanitized mirror, whereas Harness is a precedence-based configuration stack.
