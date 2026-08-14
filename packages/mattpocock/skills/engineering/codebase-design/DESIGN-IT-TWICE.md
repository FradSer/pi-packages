# Design It Twice

When the user wants to explore alternative interfaces for a chosen deepening candidate, compare distinct designs. Use parallel teammates only when the teammate facility is available; otherwise work through the designs sequentially. Based on "Design It Twice" (Ousterhout) — your first idea is unlikely to be the best.

Uses the vocabulary in [SKILL.md](SKILL.md) — **module**, **interface**, **seam**, **adapter**, **leverage**.

## Process

### 1. Frame the problem space

Before beginning the design comparisons, write a user-facing explanation of the problem space for the chosen candidate:

- The constraints any new interface would need to satisfy
- The dependencies it would rely on, and which category they fall into (see [DEEPENING.md](DEEPENING.md))
- A rough illustrative code sketch to ground the constraints — not a proposal, just a way to make the constraints concrete

Show this to the user, then immediately proceed to Step 2. The user reads and thinks while the comparisons are prepared.

### 2. Produce distinct designs

Produce 3+ **radically different** interfaces for the deepened module. If the teammate facility is available, delegate the independent briefs to separate teammates and compare their reports; otherwise produce the designs sequentially in the current context.

Give each design brief the file paths, coupling details, dependency category from [DEEPENING.md](DEEPENING.md), and what sits behind the seam. Keep it independent of the user-facing problem-space explanation in Step 1. Use a different constraint for each design:

- Design 1: "Minimize the interface — aim for 1–3 entry points max. Maximise leverage per entry point."
- Design 2: "Maximise flexibility — support many use cases and extension."
- Design 3: "Optimise for the most common caller — make the default case trivial."
- Design 4 (if applicable): "Design around ports & adapters for cross-seam dependencies."

Include both [SKILL.md](SKILL.md) vocabulary and CONTEXT.md vocabulary in each brief so the designs name things consistently with the architecture language and the project's domain language.

Each design outputs:

1. Interface (types, methods, params — plus invariants, ordering, error modes)
2. Usage example showing how callers use it
3. What the implementation hides behind the seam
4. Dependency strategy and adapters (see [DEEPENING.md](DEEPENING.md))
5. Trade-offs — where leverage is high, where it's thin

### 3. Present and compare

Present designs sequentially so the user can absorb each one, then compare them in prose. Contrast by **depth** (leverage at the interface), **locality** (where change concentrates), and **seam placement**.

After comparing, give your own recommendation: which design you think is strongest and why. If elements from different designs would combine well, propose a hybrid. Be opinionated — the user wants a strong read, not a menu.
