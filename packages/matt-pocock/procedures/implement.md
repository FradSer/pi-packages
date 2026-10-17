Implement the work described by the user in the spec or tickets.

If the user passes a ticket reference, fetch it from the issue tracker and state its title before starting. If the reference is ambiguous, ask.

Use [bdd](../references/bdd.md) at the agreed seams, one red-green slice at a time. The bundled [tdd](tdd.md) owns Automation-phase test quality, seams, and mocking guidance.

## Minimal fix

Fix the defect directly. Do not add a defensive default or fallback for a value the trusted path cannot miss: `quantity ?? 1` and `quantity || 0` are the shape to avoid. Validate once at the boundary instead of guarding at every use.

## Verification and integration

- Establish which checks are safe before execution; use isolated home, credentials and test data where needed. Do not assume local commands have no production access.
- Give implementers bounded local checks and appoint one integration owner for shared checks. Keep dependent changes ordered and conflicting writes under one owner; use the host's dependency and resource primitives when available.
- Record the task baseline, including untracked files and unrelated dirty work to exclude. After integration and local checks, identify the candidate revision or scoped snapshot. Review and final verification must inspect the same candidate; a Git commit is not required to identify it.
- Run affected tests during implementation. The integration owner runs applicable type, lint, build and broad regression checks after integration, not redundantly per Agent. Later edits invalidate affected evidence; rerun the checks and review conclusions those edits can change. Repository-required verification still applies.

Then use [code-review](code-review.md). Delivery requires the integrated candidate's applicable verification, returned blocking reviews, and findings resolved. If only required Agent results remain outstanding, yield with the workflow active; do not announce completion while waiting. A completed review assignment is evidence to assess, not automatically a PASS on the implementation.

When the user asks to commit, follow the repository's git-agent workflow rather than staging or committing directly.
