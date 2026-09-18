Two-axis review of a task-scoped candidate against an explicit baseline:

- **Standards** — does the code conform to this repo's documented coding standards?
- **Spec** — does the code faithfully implement the originating issue / PRD / spec? If the spec contains Gherkin scenarios (from [bdd](bdd.md)), those are the authoritative acceptance criteria.

For a bounded change, one fresh reviewer can assess both axes and return separate verdicts. Use separate reviewers only when scale, distinct expertise, or repository policy justifies them. Without delegation, assess Standards then Spec and preserve the reports separately. Agent count is not evidence of independence or quality.

Use the confirmed requirements already available; an issue tracker is optional. Read repository issue-tracker guidance only when the spec actually lives there. Missing tracker setup is not a reason to start setup work for a local review.

**Review-only scope:** For a standalone review request or bounded reviewer assignment, return the report with separate verdicts and findings, including REWORK, without editing the implementation and without waiting for repairs. Remediation and implementation-delivery conditions below belong to the Leader or implementation owner; they do not extend a review-only assignment. If access or evidence prevents the review itself, report that execution blocker rather than presenting unperformed checks as findings.

## Process

### 1. Pin the baseline and candidate

Record what the review judges before delegation or verification:

- **Committed comparison:** honor a supplied ref and verify it resolves. Use `git diff <fixed-point>...HEAD` and the relevant commit list for that comparison.
- **Current uncommitted task:** use the recorded task-start baseline or a scoped patch/snapshot. Include untracked files; exclude pre-existing dirty work and other Agents' unrelated changes. A plain `git diff HEAD` is insufficient when it mixes tasks. Ask only when the intended scope or baseline cannot be established from context.

Name the candidate revision or content fingerprint and provide the reviewer its exact delta, requirements and safe verification scope. Review and integration checks inspect that same candidate. Keep it stable while those checks run, or mark affected evidence stale when files change. Do not claim a result from an older candidate proves a newer one, and do not create a commit merely to identify the candidate.

### 2. Identify the spec source

Use the originating spec, explicit path or linked issue when supplied. For a local task, confirmed conversation requirements and its Given/When/Then scenarios are a valid spec; include those in the review brief rather than asking for a redundant artifact. Consult repository PRDs or issue references when context points there. Ask only for genuinely missing or conflicting requirements. If no spec exists, report the Spec axis as unavailable instead of inventing acceptance criteria or silently treating it as PASS.

### 3. Identify the standards sources

Anything in the repo that documents how code should be written, such as `CODING_STANDARDS.md` or `CONTRIBUTING.md`.

On top of whatever the repo documents, the Standards axis always carries the **smell and AI slop baselines** below — a fixed set of Fowler code smells (_Refactoring_, ch.3) plus cross-language AI slop patterns that applies even when a repo documents nothing. Two rules bind them:

- **The repo overrides.** A documented repo standard always wins; where it endorses something the baseline would flag, suppress the smell.
- **Always a judgement call.** Each smell is a labelled heuristic ("possible Feature Envy"), never a hard violation — and, like any standard here, skip anything tooling already enforces.

Each smell reads *what it is* → *how to fix*; match it against the diff:

- **Mysterious Name** — a function, variable, or type whose name doesn't reveal what it does or holds. → rename it; if no honest name comes, the design's murky.
- **Duplicated Code** — the same logic shape appears in more than one hunk or file in the change. → extract the shared shape, call it from both.
- **Feature Envy** — a method that reaches into another object's data more than its own. → move the method onto the data it envies.
- **Data Clumps** — the same few fields or params keep travelling together (a type wanting to be born). → bundle them into one type, pass that.
- **Primitive Obsession** — a primitive or string standing in for a domain concept that deserves its own type. → give the concept its own small type.
- **Repeated Switches** — the same `switch`/`if`-cascade on the same type recurs across the change. → replace with polymorphism, or one map both sites share.
- **Shotgun Surgery** — one logical change forces scattered edits across many files in the diff. → gather what changes together into one module.
- **Divergent Change** — one file or module is edited for several unrelated reasons. → split so each module changes for one reason.
- **Speculative Generality** — abstraction, parameters, or hooks added for needs the spec doesn't have. → delete it; inline back until a real need shows.
- **Message Chains** — long `a.b().c().d()` navigation the caller shouldn't depend on. → hide the walk behind one method on the first object.
- **Middle Man** — a class or function that mostly just delegates onward. → cut it, call the real target direct.
- **Refused Bequest** — a subclass or implementer that ignores or overrides most of what it inherits. → drop the inheritance, use composition.

### AI slop baseline

Language-model-generated code tends to emit low-evidence, low-signal patterns regardless of language. The smell baseline's two binding rules apply unchanged: the repo overrides, and skip any pattern that tooling already enforces (for example, a repository running dedicated anti-slop lint rules). Each pattern reads *what it is* → *how to fix it*:

- **Fabricated evidence** — casts or suppressions that assert a type or invariant the code never established: chained `as`/`as unknown as`, `cast(Any, x)`, `# type: ignore`, unjustified `@ts-ignore`, `unsafe` blocks or `.unwrap()` standing in for real handling. → parse at the boundary or guard the type; require a written invariant justification for any suppression.
- **Evidence widening** — known precise values funneled into `unknown`/`any`/`object`/`interface{}`/open dictionaries, or finite records degraded to open maps. → preserve the precise type end to end; widen only at an unparsed boundary.
- **Defensive clutter** — `try/except: pass`, redundant null checks in trusted codepaths, conditional empty-spread omission tricks, silent fallbacks. → delete the check; validate at the boundary once.
- **Mock patching** — tests that mock or monkey-patch the module's own internals instead of exercising real seams. → test through an injected adapter or the public interface.
- **Vacuous names** — symbols named after their type or shape (`data`, `info`, `obj`, `helper`, `manager`, `*Shape`) instead of their domain meaning. → rename to the domain concept; no honest name means the design is murky.

Match each pattern against the diff the same way as the smell baseline: labelled judgement calls, hard only when a documented standard forbids them, and skipped when repository tooling enforces the pattern.

### 4. Run the two independent reviews

Give the reviewer both briefs for bounded work, or one brief per reviewer when separate expertise is justified. Each brief carries the same candidate and task baseline. Workers run assigned local checks; one integration owner owns shared verification. Verify the commands' safety and isolation before execution. Continue unrelated work while required reports are outstanding; otherwise yield with the workflow active, without declaring completion. Keep the two axes separate until aggregation.

**Standards review brief** — include:

- The baseline, exact candidate, scoped diff or snapshot, and commit list if applicable.
- The list of standards-source files you found in step 3, **plus the smell and AI slop baselines from step 3** pasted in full — the reviewer needs this material to evaluate the diff.
- The brief: "Report — per file/hunk where relevant — (a) every place the diff violates a documented standard: cite the standard (file + the rule); and (b) any baseline smell or AI slop pattern you spot: name it and quote the hunk. Distinguish hard violations from judgement calls — documented-standard breaches can be hard, but baseline smells and AI slop patterns are always judgement calls, and a documented repo standard overrides the baseline. Skip anything tooling enforces. Under 400 words."

**Spec review brief** — include:

- The same baseline, candidate and scoped delta, with a commit list if applicable.
- The spec or confirmed conversation requirements and scenarios.
- The brief: "Report: (a) Gherkin scenarios (Given/When/Then) in the spec that are missing or partial; (b) behaviour in the diff that wasn't asked for (scope creep); (c) requirements that look implemented but where the implementation looks wrong. If the spec contains Gherkin scenarios, those are the authoritative acceptance criteria. Quote the spec line for each finding. Under 400 words."

If the spec is missing, skip the Spec review and note this in the final report.

### 5. Aggregate

Present the two reports under `## Standards` and `## Spec` headings, verbatim or lightly cleaned. Do **not** merge or rerank findings — the two axes are deliberately separate (see _Why two axes_).

End with a one-line summary: total findings per axis, and the worst issue _within each axis_ (if any). Don't pick a single winner across axes — that's the reranking the separation exists to prevent.

### 5.3 Owner remediation and recheck handoff

The Leader or implementation owner applies this section after receiving the review; a review-only caller proceeds to its verdict and report. A completed review Work Item means a report was delivered, not that the implementation passed. Group findings by root cause, add adjacent-case regressions, and repair the affected behavior as one bounded correction where possible. Identify the new candidate and rerun affected checks; retain unaffected evidence with its scope explicit.

Before a bounded recheck, preserve the prior findings and candidate identity in a durable review artifact. Prepare a refreshed brief with the retained baseline, new candidate fingerprint, correction delta, prior findings, and safe check scope. A reviewer must read that authoritative brief and validate the fingerprint before inspecting the candidate.

With Agent Teams, reopening does not update the description, forward prior findings, or use the reopen reason as a new assignment prompt; it clears the old result. If the original description already directs the reviewer to an authoritative brief for the current attempt, update that referenced brief before reopening, then assign an available exact session. Keep the prior report separate and the refreshed brief stable during the attempt. If the old description pins a conflicting candidate or has no such reference, use `work create` for bounded follow-up Work with the full refreshed description and `dependsOn` pointing to the completed review, then assign it. This is a linked correction check, not a new broad review. Never rewrite board files to simulate a description update.

Sending a message to a closed assignment does not restart review. If Work is still active, follow release/reassignment authority before changing its brief. Request a new broad review only when scope or risk materially changes.

The implementation owner finishes delivery only when every required report has returned, blocking findings are resolved, and verification plus review verdicts apply to the final candidate. An unrelated failing check is disclosed as a limitation, not silently turned into a pass. Outstanding required results keep the implementation workflow active; yield instead of sending a premature final delivery.

### 5.4 Memory read-before (Standards axis)

Before scoring, load the project's known traps: `Glob docs/memory/*.md`, then read every file whose frontmatter `category` is `pitfall` or `convention` and whose `summary` is topically related to this review (the diff's files, patterns, or stack). These are evaluator-verified failure modes this repo already paid for.

In step 5.5's Standards scoring, treat a read memory file as a red flag: if the diff exhibits a known pitfall, record it as a FAIL in the Standards report with evidence citing the memory file (`docs/memory/pitfall_<slug>.md`). If `docs/memory/` does not exist, skip this step.

### 5.5 Binary verdict + refute-before-PASS

After presenting the two reports, emit a binary verdict per axis:

- **Standards axis**: binary PASS (no unresolved standard violations or smells in the Standards report) / REWORK (any standard violation or listed smell).
- **Spec axis**: binary PASS (all Gherkin scenarios in the spec demonstrably implemented) / REWORK (any scenario missing/partial/wrong).

**Refute-before-PASS (red-team protocol):** Before assigning PASS to either axis, attempt to refute your own PASS:

1. State the strongest reason the work might FAIL this axis despite looking green.
2. Cite the specific evidence (diff hunk or missing scenario) that would confirm that failure.
3. Only if that failure case is itself refuted by concrete contrary evidence does PASS hold.

A PASS without an attempted refutation is invalid — downgrade to REWORK and list the un-refuted risk.

**Final verdict:** REWORK if either axis is REWORK; PASS only if both axes PASS (post-refutation).

## CRITICAL: Refute-before-PASS

A PASS without an attempted refutation is invalid. Before assigning PASS to either axis, state the strongest reason the work might still fail, cite the evidence (diff hunk or missing scenario) that would confirm it, and hold PASS only when concrete contrary evidence refutes it. Never merge or rerank the two axes — the separation exists to stop one axis masking the other.

## Why two axes

A change can pass one axis and fail the other:

- Code that follows every standard but implements the wrong thing → **Standards pass, Spec fail.**
- Code that does exactly what the issue asked but breaks the project's conventions → **Spec pass, Standards fail.**

Reporting them separately stops one axis from masking the other.
