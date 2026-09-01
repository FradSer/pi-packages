# Behavior-Driven Development (BDD)

BDD is not just about tools; it's a methodology for shared understanding and high-quality implementation. This skill governs the **Discovery → Formulation → Automation** lifecycle: Gherkin scenarios define the behavior, and the Automation phase (red-green loop) is delegated to [tdd](tdd.md) (BDD-driven).

When exploring the codebase, read `CONTEXT.md` (if it exists) so test names and interface vocabulary match the project's domain language, and respect ADRs in the area you're touching.

## How to Use This Skill

When the user asks for a feature, bug fix, or refactor, apply the following mindset:

1.  **Understand Behavior First:** Do not start coding until you know *what* the system should do.
2.  **Define Scenarios:** Create or ask for concrete examples (Gherkin) of the expected behavior.
3.  **Drive Implementation with Tests:** Use the Red-Green-Refactor cycle.

## The BDD Cycle

The process flows from requirements to code:

*   **Discovery:** Clarify requirements through examples (The "Three Amigos").
*   **Formulation:** Write these examples as specific scenarios (Given/When/Then).
*   **Automation:** Implement using the red-green-refactor cycle via [tdd](tdd.md), which governs test quality, seams, mocking, and anti-patterns.

See `./references/bdd-best-practices.md` for a detailed guide.

## Writing Scenarios (Gherkin)

Scenarios are your "Executable Specifications".

*   Keep them declarative (business focus).
*   Avoid technical jargon and UI details.
*   One behavior per scenario.
*   **Store executable scenarios in `.feature` files or the framework-native executable test format** — not as code comments. Once implementation begins, translate the scenarios that will be automated into `.feature` files or the framework-native executable test format, so they double as living documentation.

See `./references/gherkin-guide.md` for syntax and storage structure.

## Automation Phase

The Automation phase (red-green loop) is governed by the [tdd](tdd.md) skill (BDD-driven). When the Gherkin scenario is defined and the seam is agreed, invoke [tdd](tdd.md) for:

- **Seams** — where tests go at the public boundary
- **Test quality** — what makes a good test, anti-patterns
- **Mocking** — when to mock and at which boundaries
- **Red-green loop rules** — one slice at a time, refactor after green

## Seams — where tests go

Seams are the public boundaries you test at. See [tdd](tdd.md) for the full seam guidance.

**Test at the highest established seam.** Before writing a test, inspect the existing public boundaries, record the seam under test, and choose the highest one that expresses the confirmed behavior. Testing everything isn't possible — deliberately choosing the critical public seam is how effort lands on complex behavior instead of every edge case. Ask the user only when the behavior or public-contract choice is genuinely unresolved; otherwise begin the red-green loop immediately.

## What a good test is

Tests verify behavior through public interfaces, not implementation details. See [tdd](tdd.md) for the full guidance, examples, and anti-patterns.

## CRITICAL: The Iron Law

> **"No production code is written without a failing test first."**

The Red step MUST verify the test fails for the right reason (run the test and read the failure output) before writing any implementation. Skipping or rationalizing this step produces:

1.  Tests that pass spuriously — you cannot tell if they are capable of failing.
2.  Implementation-biased tests — they reflect the code that was written, not the behavior under contract.
3.  Legacy code from day one — no behavioral safety net catches future regressions.

### If Production Code Already Exists

Delete it and re-derive it from a failing test — do not keep it "as reference," do not "adapt" it into the test-first version, do not read it while writing the test. Any of those re-introduces the implementation-biased-test failure mode above through the back door: a test written while looking at the code it's meant to constrain will pass on the first try regardless of whether it checks the right thing. Delete means delete.

### Common Rationalizations (reject all of these)

| Rationalization | Why it fails |
|---|---|
| "I'll write the test after — same coverage either way" | A test written against working code always passes on the first run. That proves the test doesn't crash, not that it verifies the right behavior. Only a test that failed first, for the stated reason, has been shown capable of catching a regression. |
| "I already manually verified it works" | Manual verification is not repeatable and leaves no regression guard. It answers "did this work once," not "will this keep working." |
| "This is too simple to need a test" | Simple code changes behavior just as easily as complex code. The Iron Law has no complexity threshold — it has the three named exceptions below and nothing else. |
| "I'll be pragmatic, not dogmatic, about BDD-driven TDD" | This is the rationalization, not an alternative to it. Every one of these tables' entries is someone being "pragmatic" about skipping the Red step. |
| "I already spent an hour on this, deleting it is wasteful" | Sunk cost. The hour is already spent whether you delete the code or keep it; keeping untested code doesn't recover that hour, it just adds an unverified regression risk on top of it. |

The only legitimate exceptions are named in `./references/bdd-best-practices.md` (one-off prototypes, generated code, config files) — and even those should be raised with the user, not silently assumed.

### Tests Written After the Fact Answer a Different Question

A test-first test encodes "this is what the system is contracted to do." A test-after test encodes "this is what the code I already wrote happens to do" — it will pass even if the code has the wrong behavior, because it was shaped to match that behavior rather than an independent specification. If you catch yourself writing a test against code you can already see, stop, delete the code, and write the test against the *behavior* instead.

## Rules of the loop

See [tdd](tdd.md) (BDD-driven) for the full red-green loop rules, anti-patterns, and test quality guidance. The key points:

- **Red before green.** Write the failing test first, then only enough code to pass it.
- **One slice at a time.** One seam, one test, one minimal implementation per cycle.
- **Refactoring is not part of the loop.** It belongs to the review stage (see [code-review](code-review.md)), not the red → green implementation cycle.

## References

- `./references/bdd-best-practices.md` - BDD methodology: discovery, formulation, automation
- `./references/gherkin-guide.md` - Gherkin syntax, storage structure, examples
- `./references/testing-anti-patterns.md` - Mocking pitfalls and vacuous-passing tests
- [tdd](tdd.md) - BDD-driven test implementation: seams, mocking, test quality, red-green loop
