# Phase boundaries

A **phase** is a chunk of work inside a session — the grilling, the implementation, the QA. The definition is fuzzy on purpose: a phase ends when you think *"ok, we're done with that"*.

The **phase boundary** is the gap between two phases, and it is the only place this decision belongs. Mid-phase there is no decision to make — continue, or delegate the work that remains to a teammate when that facility is available. Compacting mid-phase makes the agent lose the thread.

## The five options

| Option       | What it does                                                    |
| ------------ | --------------------------------------------------------------- |
| **Continue** | Stay in the session. No context switch at all.                    |
| **`/new`** | Start a fresh session when the old context is irrelevant.          |
| **[handoff](handoff.md)** | Write a portable Markdown document; it does not create, fork, or seed a session. |
| **Teammate** | Delegate a tightly scoped task when the teammate facility is available. |
| **`/compact`** | Compress this context and seed a fresh session with the summary.  |

## The tree

Work top to bottom at the boundary. The first **yes** wins.

**1. Can you continue in this session?** Two things make the answer yes: the next phase needs this phase as a **primary source**, or you have enough [smart zone](https://www.aihero.dev/ai-coding-dictionary/smart-zone) left (~150k tokens) for the next phase to fit. Grilling → implementation is the standard yes: the implementation wants the reasoning verbatim, not a summary of it. Continue costs nothing and loses nothing, so rule it out before anything else.

**2. Is the context irrelevant to what comes next?** Is everything in this session — the exploration, the decisions, the dead ends — disposable? If so, start a fresh session with **`/new`**. The old session remains resumable.

The cost of getting this wrong is one-way. Leave a *relevant* context and you lose the **why** behind what you built, and no amount of reading the diff back gets it returned.

**3. Do you need to hand off?** [handoff](handoff.md) is narrow. You need it only when you are:

- swapping to a **new harness** (one harness → another harness),
- moving to a **new directory** or repo,
- sending the work to a **colleague**,
- or recording a side task you found **mid-phase** without derailing what you're doing.

That list is the whole clause. What [handoff](handoff.md) buys is **portability** — a document that travels. It only writes the document; it does not create, fork, or seed a session. If nothing is travelling, you don't need it.

**4. Can the task be done AFK?** Is it scoped tightly enough to run with you away from the keyboard, no steering? If the teammate facility is available, delegate it to a teammate and leave this session untouched. Otherwise complete it sequentially in the current context. Automated review is the standard case: the reviewer reads the diff and reports, and you aren't needed while it does.

**5. Otherwise, `/compact`.** Relevant context, same harness, same directory, and you need to stay in the loop — this is where the tree lands, and it lands here often. Pass it an instruction (`/compact we're going to QA this area`) so the summary keeps what the next phase needs.

`/compact` is the **default, not the first reach**. It sits at the bottom because the four questions above it are all cheaper or more precise. The failure mode when people start here is a fresh session that is confidently wrong about a decision the summary flattened.

## Primary and secondary sources

Every move except **Continue** turns a **primary source** into a **secondary source** — the session as it happened, replaced by a summary of it. The trade is always the same shape:

| Source                            | Information | Noise | Room to move |
| --------------------------------- | ----------- | ----- | ------------ |
| Primary (Continue)                | Full        | Lots  | Little       |
| Secondary (`/compact`, [handoff](handoff.md)) | Lossy       | Less  | Lots         |

This is why question 1 comes first. You only pay the lossiness when staying costs more than it saves.

## These are judgement calls

The questions are not objective — each has taste in it, and the same boundary can go two ways on two days. The value is in asking them **in order**, at the boundary rather than in the middle of the work.
