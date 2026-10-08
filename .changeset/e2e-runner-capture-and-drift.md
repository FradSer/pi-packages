---
"@fradser/pi-e2e": patch
---

Acceptance verification reports the real cause, captures its current runner for each attempt, and can reach a fulfilled verdict.

Seven defects kept a changed feature from ever clearing its checkpoint. Each one is fixed with a
regression test that failed first.

**Every attempt captures its current runner configuration.** Feature snapshots use a dedicated
turn token, so concurrent tool activity cannot lose turn-scoped capture; a new input or reset
invalidates stale work. Runner and adapter capture belongs to each verification attempt, allowing
repairs and repeated fresh runs in the same turn.

**A rejection names its cause.** Missing or invalid configuration reports the actual read or
validation error. A stale turn says the turn changed. Adapter changes during an attempt name the
files that differ, using `runnerDrift` to compare bounded snapshots.

**The harness does not re-read its own prompt.** A checkpoint arrives as an ordinary user message
and names both `e2e_verify` and a `.feature` path, so `recordUserPrompt` treated it as a new user
acceptance request and re-armed acceptance every turn. A prompt carrying either checkpoint marker is
now ignored for user-request parsing.

**Naming a feature is not changing it.** A shell command that merely mentioned a `.feature` path
marked that file as explicitly changed, so running a feature's own tests re-armed its checkpoint.
Shell-derived paths now record involvement only, and the snapshot comparison decides whether the
content changed. A shell expansion is not a path either: `"$PWD/x.feature"` no longer becomes
`<cwd>/PWD/x.feature`, absolute paths are matched, and a shell-derived path must stay inside the
working tree.

**The adapter can certify.** The project adapter declared `adjudicableClauses: []`, which suppressed
every clause from judgment: zero questions asked, every clause unjudged, `needs_review` for any run,
however correct. It now emits one deterministic check per Then clause from the scenario-to-test
mapping, so a clause is decided in code with no model call. The scenario-to-test mapping is the
project's trust declaration; the adapter cannot prove that a mapped test tests the right business
behavior. `packages/e2e/features/e2e.feature` gains that mapping for all 23 scenarios, and the
adapter accepts `packages/e2e/tests` references.

**The settled notification reports a state once.** `notifyOnSettled` ran on `agent_settled` and
re-emitted the same "changed .feature file(s) remain unverified" warning at every settlement, because
it had no deduplication while `checkBeforeSettle` did. A turn that never ran `beginTurn` — Pi delivers
an extension's `followUp` message without an `input` event — inherited the previous turn's state and
re-warned about it indefinitely. The notification now builds a fingerprint from the pending set, the
continuation count, the progress revision, the failed-verdict count and the request flags, and reports
a state once. It also derives its count from the pending set rather than the raw modified set, so a
feature that needs no verification can neither warn nor suppress the success notice.

**The English README** now states the involvement rule the code implements, per-attempt rejection
causes, and that an adapter must declare checks for the clauses it can decide.
