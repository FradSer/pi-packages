# 0005: Preserve installed Harness protections across upgrades

## Status

Accepted after an actual upgrade regression. Supersedes the legacy-retirement
portion of `packages/continual-learning/HARNESS-DESIGN.md`, not the flat authoring
model or parent-owned learning safety gates.

## Context

The flat `rules` rollout rejected existing `policies`/`skillPrompts` files as
unavailable configuration. This project had two valid, narrow write/edit
policies in `.pi/harness.local.json`. Neither applied to Bash, yet rejecting the
container made every Bash call fail closed. Removing or temporarily disabling
the file would also remove its intended protections. New-format fixture tests
did not cover an installed user's upgrade path.

## Decision

- Flat `rules` remain the format for new authoring and learning.
- Existing policy and skill-prompt declarations remain supported runtime input
  through an explicit compatibility boundary. Their matching, precedence,
  disablement, confirmation and post-generation semantics are preserved; a
  weaker flat rule is not an equivalent migration. Existing cumulative disabled
  names retain the historical same-ID effect on saved flat rules as well as
  legacy policies; an upgrade must not reactivate a paused identity.
- Loading is read-only. No upgrade rewrites, deletes, disables or silently
  replaces user configuration. New flat additions preserve existing containers.
- Compatible legacy data is not invalid configuration. Compatibility notices
  remain separate from errors and do not create unrelated execution blocks.
- An invalid declaration restricts only operations its known scope can affect.
  Unknown scope or unreadable configuration remains conservatively diagnosed;
  unrelated diagnosis and explicitly authorized repair paths stay available.
- Explicit replacement requires a concrete preview and authorization bound to
  exact tool arguments and predecessor bytes. Parameter or configuration changes
  during any confirmation invalidate approval. The raw-byte snapshots survive
  later policy prompts and are rechecked after the final asynchronous approval;
  equal resolved diagnostics are not evidence that raw configuration is unchanged.
  Execution-policy resolution follows asynchronous preflight; an earlier cached
  resolution cannot govern a later approved configuration snapshot.
  Recovery of incomplete
  configuration does not bypass valid policies protecting configuration files.
  New learning cannot claim ownership of legacy manual or learned policies.

## Verification contract

Test a saved old-format file across the new loader and actual registered hooks,
not only a parser. For the narrow write/edit fixture, harmless Bash must proceed
while prohibited new content is still blocked; removing prohibited old text must
remain allowed. Read-only loading must leave every configuration byte unchanged.
Cover mixed-format precedence, confirmation, invalid scoped declarations, legacy
skill/output/artifact behavior, and new flat additions without protection loss.

## Consequences

A bounded compatibility implementation costs more code than immediate removal,
but it prevents an upgrade from weakening protection or locking unrelated work.
Retirement requires an explicit future release decision with verified migration
coverage; it cannot be inferred from a request to simplify prompts or schemas.
