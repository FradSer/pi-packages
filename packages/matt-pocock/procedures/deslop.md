# De-slop

Remove AI slop from a bounded change set without changing behavior. AI slop is the set of low-evidence, low-signal patterns that language-model-generated code tends to emit under completion pressure: fabricated evidence, discarded type information, defensive clutter, test-cheating seams, and vacuous names. The categories are language-neutral — this capability applies them to whatever stack the change set touches, not just TypeScript.

Run this as a focused pass over a diff, an uncommitted change set, or named files. It never adds features, never changes public behavior, and never trades a working product for cleanup. Tests and types must stay green; if the change set has no test coverage, report that and stop before rewriting anything.

## The five slop categories

Each category reads *what it is* → *how to fix it*. Match them against the change set:

- **Fabricated evidence** — casts, suppressions, or unsafe escapes that assert a type or invariant the code never established: chained `as`/`as unknown as`, `cast(Any, x)`, `# type: ignore`, `@ts-ignore`/`@ts-expect-error` without justification, `unsafe` blocks or `.unwrap()` standing in for real handling, non-null `!` assertions on nullable values. → Replace with boundary parsing, type guards, or pattern matching; when a suppression is genuinely required, pair it with a non-empty invariant justification.
- **Evidence widening** — known, precise values funneled into top types or open dictionaries: parameters and returns typed `object`/`unknown`/`any`/`interface{}`/`dict[str, Any]`, finite records degraded to open maps, `as any` to silence a mismatch. → Preserve the precise type end to end; widen only at an unparsed boundary and parse there.
- **Defensive clutter** — no-op protection against cases a trusted codepath cannot produce: `try/except: pass`, redundant null checks inside internal call chains where the value is guaranteed, conditional empty-object spreads and similar omission tricks, silent fallback defaults. → Delete the check; validate at the boundary once instead of everywhere.
- **Mock patching** — tests that monkey-patch or mock a module's internals to force the code under test to pass: `patch("module.path")` on the subject's own collaborators, `vi.mock`/`jest.mock` on internal modules, snapshots derived from the implementation. → Test through real seams: inject an adapter, point the code at an in-memory implementation, or exercise the public interface.
- **Vacuous names** — symbols named after their type or shape instead of their domain meaning: `data`, `info`, `item`, `result`, `obj`, `helper`, `manager`, `*Shape`, `handleX`. → Rename to the domain concept the symbol carries; if no honest name exists, the design is murky and that is a finding, not a rename.

Two binding rules:

- **Repo tooling overrides.** If the repository enforces a category through lint or CI (for example vendored anti-slop Oxlint rules), skip it here — tooling already rejects it, and duplicating it wastes effort.
- **Behavior is frozen.** Every rewrite must keep observable behavior, public interfaces, and test outcomes identical. A de-slop pass that requires a behavior change is out of scope — record it as a finding instead.

## Process

### 1. Pin the scope

Resolve the change set before touching anything:

- If the user named a diff base, files, or a review request, use that.
- Otherwise use the uncommitted change set (`git status` plus `git diff`).
- An empty scope is a stop: report that there is nothing to de-slop.

### 2. Inventory findings

Scan the scope once per category. Produce a findings list: category, location (file plus hunk), the offending line quoted, and the replacement plan. A finding without a concrete replacement plan is not ready to fix — leave it as a reported finding.

### 3. Rewrite

Apply the plans in one pass, category by category. For each rewrite:

1. Replace the slop with the typed, seam-based, or renamed equivalent.
2. Keep tests green after each category batch; run the repository's test suite or the affected subset between batches.
3. Stop and report when a planned rewrite cannot keep tests green — the slop was load-bearing, which is itself a finding.

### 4. Verify

Run the verification the repository already uses — tests, typecheck, and lint. A de-slop pass ends green or it has not ended.

### 5. Verdict

Report under three headings:

- **Removed** — each rewrite as `category → file:line → one-line replacement summary`.
- **Findings** — slop that could not be removed without a behavior change, test coverage, or a design decision, each with the reason.
- **Skipped** — categories skipped because repository tooling already enforces them.

End with a binary verdict: **CLEAN** only if every planned rewrite landed and verification is green; **PARTIAL** when findings remain. Never report CLEAN with unverified skips.
