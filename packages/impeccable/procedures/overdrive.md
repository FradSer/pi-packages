# Push an interface past conventional limits

Adapted from Impeccable `skill/reference/overdrive.md` at `cd12f8660e2dde57b9615c8a6b8ea674101f9cfc`, Apache-2.0. Modified: Pi tool boundaries and manual direction approval replace upstream question-tool and browser-automation loops, bounded verification replaces open-ended iteration. See package licenses and notices.

Overdrive uses the full power of the browser to make an existing part of an interface feel extraordinary: a table that stays smooth at scale, a dialog that morphs from its trigger, a form that validates with streaming feedback, a transition that feels cinematic. Context decides what extraordinary means: spectacle on a creative portfolio can impress while the same spectacle on a settings page embarrasses; a settings page with instant optimistic saves and animated state transitions can be extraordinary on its own terms. This command changes how an existing feature feels, never what the product does.

## Establish scope and evidence

Follow [target setup](setup.md). Run `node {{PKG_DIR}}/scripts/context.mjs`, adding `--target <path>` when the user names one, and inspect the target surface and its personality before choosing a technique. Decide what would make a user of this specific interface say the experience is better: sensory craft for visual surfaces, felt responsiveness for functional UI, invisible performance for critical paths, fluidity for data-heavy views. Fix weak design fundamentals through other commands first; technical ambition must not mask them.

Use [principles](../references/taste/principles.md), [components](../references/taste/components.md) and [motion](../references/taste/motion.md) as the rule owners. If platform scope arises, native guidance is reported unavailable per setup.

## Propose before building

This command misfires hardest, so never jump straight to implementation. Think through two or three directions with different techniques, ambition levels and aesthetic approaches; describe what each would look and feel like with its trade-offs in browser support, performance cost and complexity. Present the directions to the user and wait for an explicit pick before writing code. Proceed only with the confirmed direction.

Build with discipline. Every technique degrades gracefully so the experience without the enhancement still holds up; prefer feature checks and layered fallbacks, lazy-initialize heavy resources only near the viewport, and pause off-screen work. Target full frame rate on mid-range hardware and simplify when it drops. Close with refinement rather than the first working version: easing, timing offsets and secondary motion are what separate extraordinary from merely functional.

NEVER:

- Ship effects that jank on mid-range devices.
- Depend on a new API without a functional fallback.
- Add sound without explicit user opt-in.
- Use spectacle to cover weak fundamentals.
- Layer multiple competing extraordinary moments; focus creates impact, excess creates noise.
- Add product scope such as collaboration, offline support or backend capability under this command.

## Verify and finish

Build the confirmed direction, inspect it on desktop and mobile widths where supported, fix observed defects in one batch, then perform at most one confirmation round. Where the change touches a local web file, one optional detector pass is allowed: `node {{PKG_DIR}}/scripts/detect.mjs --json <local-file>` on local files only, never URLs, web-only. A clean scan is not proof of design quality. If device or browser verification is unavailable, mark those cases unverified.

Apply the removal, device and context checks: does taking the enhancement away diminish the experience, does it stay smooth on modest hardware, and does it fit this brand and audience. Report what changed, concrete verification results, intentional exceptions and remaining limitations. Do not launch another capability or agent as an automatic finish handoff; naming `/impeccable polish` as a possible next step stays inline code, never an action.
