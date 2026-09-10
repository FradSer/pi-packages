# Shape the brief before building

Adapted from Impeccable `skill/reference/shape.md` at `cd12f8660e2dde57b9615c8a6b8ea674101f9cfc`, Apache-2.0. Modified: folded direction resolution into the brief so no separate world contract is needed, replaced structured tool calls with conversation asks, dropped launcher references. See package licenses and notices.

Shape discovers what should be made and how it should work, then returns a confirmed design brief. It never writes code.

## Interview in rounds

Do not write code or choose visual direction yet. Follow [target setup](setup.md): establish the shipping constraints and read the neighboring surfaces before asking anything.

Ask two or three related questions per round, then wait for the answer. One round is the default; add a second only when the answers expose a material gap. Do not dump a questionnaire, repeat settled facts, or turn obvious facts into menus. Assert the likely reading and invite correction. A sparse prompt requires at least one answer round; a precise prompt may need only a compact confirmation. There is no user-question tool: ask the user via conversation and proceed only on confirmation.

Round 1 covers purpose, people, and outcome. Choose the two or three questions that most change the result: what the surface is for and what problem it must solve; who reaches it, in what situation and state of mind; the primary thing they must understand or do and what success looks like; what is uniquely true here that a neighboring product or generic template could not claim.

Round 2 covers material, behavior, and boundaries, and runs only for material unresolved decisions: what real content, evidence, data, and assets the experience must carry, with realistic minimum, typical, and maximum ranges; which states and transitions matter (first-run, empty, loading, error, success, permissions, overflow, expert use); the intended fidelity, breadth, and interactivity (exploration, production-ready screen, full flow, or broader surface); what must remain untouched and what would make the result feel wrong even if it looked polished; which platform, framework, performance, accessibility, localization, or delivery constraints are binding.

Never ask for CSS values or canned aesthetic lanes. Use [principles](../references/taste/principles.md), [components](../references/taste/components.md), and [motion](../references/taste/motion.md) as rule owners only where the brief needs them; do not set numeric defaults here.

## Resolve direction inside the brief

Shape is self-contained: there is no separate world contract to hand off to. When the project already has a coherent visual world, name it as the visual authority and use its composition and interaction patterns unless they are materially open. When no coherent world exists, record the direction thesis directly in the brief: the structural and interaction thesis, the sequence, the focal moment, and what that choice costs to implement. Intent, not CSS.

## Write the smallest useful brief

Write the smallest brief that lets a builder proceed without inventing product decisions:

1. **Job and audience:** who arrives, their context, need, and visitor mode.
2. **Outcome and proof:** primary task and action, what success looks like, the real evidence carried, and the product-specific truth.
3. **Selected direction:** visual authority, structural and interaction thesis, sequence, focal moment, and implementation consequence.
4. **Scope and boundaries:** fidelity, breadth, interactivity, the named target, what remains untouched, and explicit anti-goals.
5. **States and ranges:** realistic content and data ranges plus the material states.
6. **Interaction and layout:** hierarchy, topology, responsiveness, affordances, feedback, and transitions; intent, not CSS.
7. **Constraints and open decisions:** platform, delivery, accessibility, localization, reusable components, and the choices a builder must not invent.

Use three to five bullets when the task is settled; use the full structure only for ambiguous, multi-screen, or standalone planning. Do not restate the conversation.

## Confirm and stop

Present the brief for explicit confirmation or one correction round, then stop. Shape never writes code and never records a direction contract elsewhere.

When no human can answer, mark assumptions plainly in the brief, return it, and stop.

## Never

- Never write code, styles, or component scaffolding during shape.
- Never turn settled facts into further questions or dump a questionnaire.
- Never ask for CSS values, palettes, typefaces, or canned aesthetic lanes.
- Never leave the brief unconfirmed while starting build work.
- Never launch another capability or agent as an automatic finish handoff.

## Report and stop

End with a short report: what was written, what was decided and what remains explicitly undecided, how the brief was verified against existing context, and the limitations a builder must respect. Then stop.
