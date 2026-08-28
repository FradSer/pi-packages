Implement the work described by the user in the spec or tickets.

Use [bdd](bdd.md) where possible, at pre-agreed seams. During the Automation phase, load [tdd](tdd.md) (BDD-driven) for test quality, seams, and mocking guidance.

Run typechecking regularly, single test files regularly, and the full test suite once at the end.

Once done, use [code-review](code-review.md) to review the work.

## CRITICAL: BDD at pre-agreed seams, review before commit

Use [bdd](bdd.md) where possible, one red-green slice at a time at pre-agreed seams. Load [tdd](tdd.md) (BDD-driven) during the Automation phase for test quality, seams, and mocking guidance. When the work is done, run [code-review](code-review.md) over it — a change without the two-axis review is not finished work.

When the user asks to commit, follow the repository's git-agent workflow rather than staging or committing directly.
