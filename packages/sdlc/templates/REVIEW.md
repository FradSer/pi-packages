# Review policy

## Passes
- Bugs: Check behavior, failure paths, edge cases and regressions.
- Security: Check permissions, secrets, injection and data classification.
- Compliance: Compare the diff with INTENT.md, SPEC.md, PLAN.md and current policies.

## Severity
Important means broken behavior, a security exposure or a policy violation.
A Nit does not block. Report at most five Nits. Skip generated output and checks
that CI already enforces. Cite paths, evidence and the requirement or plan step.

## Ownership
A code owner approves. The authoring agent cannot approve its own change.
Record findings and fixes in the PR. A repeated mistake updates project guidance
in the same reviewed change. Review this policy and finding quality monthly.
