# Review policy

## Passes
- Bugs: Trace changed behavior and affected callers beyond the diff, including
  tests, fixtures, configuration, registrations and exports. Check failure paths,
  edge cases and regressions. Judge concurrency, data growth and performance
  against evidenced expected load; state assumptions when load is unknown.
- Security: Check permissions, secrets, injection, privacy and data classification.
  Confirm simplification preserves required validation, error handling and data integrity.
- Compliance: Compare connected behavior with INTENT.md, SPEC.md, PLAN.md and current
  policies, including accessibility. Check completeness, suitable reuse and shared
  fixes. Flag unnecessary dependencies, abstractions or duplication with concrete evidence.

## Severity
Important means broken behavior, a security exposure or a policy violation.
A Nit does not block. Report at most five Nits. Skip generated output and checks
that CI already enforces, but inspect their consumers when behavior can break.
Each finding names a concrete trigger, consequence, path and evidence, the relevant
requirement or plan step, and the smallest sufficient fix. Verify references before
calling code unused, including dynamic references and configuration. Style preference
and line count alone do not block. A documented limitation is still a finding if it
violates an accepted requirement, policy or current operating condition.
End with a verdict and Not checked: unread paths, assumptions and checks not run.
An empty finding list is not proof that unexamined behavior is correct.

## Ownership
A code owner approves. The authoring agent cannot approve its own change.
Record findings and fixes in the PR. A repeated mistake updates project guidance
in the same reviewed change. Review this policy and finding quality monthly.
