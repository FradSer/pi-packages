# 0011: Fold whitespace in private storage scope names

## Status

Accepted 2026-11-04, after a one-time explicit migration of the affected local
data. Supersedes no earlier ADR. No learning threshold, semantic gate, privacy
rule, mutation authority or evidence-bound value changed.

## Context

`escapedProjectPath` derived a readable flat scope key by stripping the leading
slash and replacing path separators and colons with dashes. It left whitespace
and control characters untouched, so a project at
`/Users/FradSer/Documents/Home Lab/1984` produced
`--Users-FradSer-Documents-Home Lab-1984--`. That name became part of every
private Memory, history, runs, scopes, locks and learning path. Paths with
literal spaces are awkward to quote, copy and inspect, and the user asked for
them to be normalized.

The same package also called its storage path validator with `create = true`
from read-only probes (backlog inspection and replay-state reads). That created
an empty per-project directory under `learning/` for every inspected project;
22 such directories existed locally. Those are intermediate artifacts, unlike
the backlog index, its cursor, completion acknowledgments and completed attempt
ledgers, which are cross-session state used by `/consolidate backfill`, crash
recovery and cost accounting.

Pi core generates `sessions/` names with its own copy of the original escaping
rule, and the goal package generates `goals/` names. Neither is owned by this
package.

## Decision

- Whitespace and control characters are folded into a single dash in the scope
  key. Paths without whitespace keep their existing readable name, so all
  existing scopes remain addressable.
- Read-only probes validate paths without creating directories. Directory
  creation is deferred until an actual write, and a released replay lease
  removes a scope directory only while it is empty (`rmdir`, which refuses a
  non-empty directory). Locks and leases are deleted on release.
- Cross-session state is retained: backlog index, scoped cursor and completion
  acknowledgments, and attempt ledgers that hold receipts. An empty scope
  directory is never created just to hold a lease.
- The local data migration is one-time and explicit, with a backup; the runtime
  has no compatibility branch that reads old names. Historical JSON that embeds
  the old scope key is not rewritten because those values are bound to frozen
  digests. Pi core `sessions/` and the goal package `goals/` are untouched.
- No editor-specific behaviour, configuration or concept is introduced.

## Alternatives considered

| Alternative | Rejected because |
| --- | --- |
| Keep the old escaping and quote paths at call sites | Every caller, script and human inspection would need to handle literal spaces; it does not fix the stored name itself. |
| Runtime lazy migration with a compatibility read of old names | The package's configuration contract has no legacy fallback, and a long-lived compatibility branch would keep two naming rules in every path computation. |
| Delete completed attempt ledgers when a replay succeeds | Those receipts are required for ack-breakpoint recovery after a crash and for retained-cost accounting. Removing them would weaken an existing validation and recovery contract. |
| Move all learning state to a temporary directory | It loses cross-session backfill and duplicate-learning protection. |
| Rewrite embedded historical scope keys during migration | Those values are bound to frozen digest chains; rewriting evidence to make paths match would corrupt the very evidence the gates protect. |

## Verification contract

- `tests/memory-storage-paths.test.ts` covers plain-path stability, interior
  whitespace folding, leading/trailing/repeated/control whitespace, no empty
  learning scope directory from inspection, lease release or empty replay, and
  preservation of a retained attempt ledger and completion record.
- `tests/test_memory_security.py` and `features/consolidate.feature` carry the
  updated readable-name contract; `features/learning-state-integrity.feature`
  carries the storage-hygiene scenarios.
- The one-time migration is verified by: zero whitespace-named paths under the
  package-owned roots, unchanged file counts for migrated Memory/history/runs,
  backlog rows all carrying the folded scope key, and `sessions/` and `goals/`
  left untouched. Historical embedded scope keys remain byte-identical.

## Consequences

A project whose canonical path contains whitespace gets a different private
scope name than before. This release requires the one-time migration described
above; an installation that changes the code without migrating its existing
private data will not see that project's earlier Memory. Historical run
manifests retain the old embedded scope key, so origin validation for those
specific old runs may refuse them; the affected local history records were
`proposed` with zero applied changes. `sessions/` and `goals/` names still
contain literal spaces because their owners define those names.
