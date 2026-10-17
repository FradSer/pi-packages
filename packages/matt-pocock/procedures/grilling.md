Interview the user relentlessly until you reach a shared understanding. Map this as a **design tree**: every decision branches into the decisions that hang off it.

Work the tree in **rounds**. The **frontier** is every decision whose prerequisites are already settled: the questions you can ask _now_ without guessing at answers you haven't heard yet. Ask the whole frontier in one round: number each question and give your recommended answer. Then wait for the user's answers before the next round.

Format a round like so:

```
❓ **Q1** - **<question title>**: <question body, might be multiple paragraphs, including multiple choices>

➡️ <your recommended answer>

---

❓ **Q2** - **<question title>**: <question body, might be multiple paragraphs, including multiple choices>

➡️ <your recommended answer>
```

Word each question so "yes" accepts your recommended answer.

Each round the user answers reshapes the tree: settled decisions push the frontier outward and unblock questions that depended on them. Recompute the frontier and ask the next round. A question whose answer depends on another question still open in this round belongs to a _later_ round, not this one.

Finding _facts_ is your job, never the user's. When a frontier question needs a fact from the environment (filesystem, tools, etc.), use a teammate when the teammate facility is available, otherwise look it up yourself; don't ask the user for anything you could look up. Don't block on it: a running exploration is an unsettled prerequisite, so only the questions downstream of it wait; ask the rest of the frontier now. The _decisions_ are the user's: put each to them and wait.

The session is done when the frontier is empty: every branch of the design tree visited, nothing left silently assumed. Do not act on it until the user confirms you have reached a shared understanding.

## CRITICAL: One question at a time — facts you look up, decisions the user makes

In this harness a frontier round is delivered through `matt_pocock_ask`, one question at a time. For each frontier question: give 2–4 concise alternatives, put your recommended answer first marked "(Recommended)", pass that same string as the required `recommended` value, and leave room for a different answer through custom input. The deadline adopts the recommendation and continues the workflow, so no question waits indefinitely. A round is complete when the user has answered every question on the frontier. Asking several questions inside one selector is bewildering.

If a *fact* can be found by exploring the environment (filesystem, tools, etc.), look it up rather than asking. The *decisions* are the user's — put each one to them, and do not act until they confirm shared understanding. Treat explicitly approved decisions already recorded in the task or authoritative spec as confirmed shared understanding: do not reopen them, invent new policy choices, or require a second confirmation. Ask only for unresolved decisions that affect the requested scope.

For an approval-required external or destructive action, recommend the option that does not act, because the deadline adopts it. Cancellation or interruption leaves the decision pending, not adopted. Once shared understanding is confirmed and the decisions are recorded, do not ask whether to continue or request separate permission for the next step: begin the next applicable workflow work immediately.

When running this procedure as a standalone capability, ask in conversation because workflow-only question tools are unavailable.
