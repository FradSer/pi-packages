# Add delight at earned moments

Adapted from Impeccable `skill/reference/delight.md` at `cd12f8660e2dde57b9615c8a6b8ea674101f9cfc`, Apache-2.0. Modified: Pi tool boundaries replace upstream handoffs, manual clarification and bounded verification replace upstream question-tool and polish-handoff automation. See package licenses and notices.

Delight is product character revealed at a moment that earns it: a useful interaction, a humane response, or an unexpectedly considered detail. It is never a layer of generic whimsy spread over the surface. Do not manufacture a celebration for an ordinary click.

## Establish scope and evidence

Follow [target setup](setup.md). Run `node {{PKG_DIR}}/scripts/context.mjs`, adding `--target <path>` when the user names one, and inspect the target, its product voice and its emotional context before proposing anything. A persuasion surface may carry personality through voice, composition, motion and discovery while the artifact stays the focus; a tool or reading surface concentrates delight at first use, completion, recovery or mastery, with reliability carrying everything else.

Look for effort worth acknowledging, waiting that can become informative, an empty or first-use state that can orient, an error moment that needs empathy, an interaction whose response could express the brand, or a useful capability people might enjoy discovering. If the emotional range or the stakes cannot be inferred, stop and ask the user rather than guessing.

Use [principles](../references/taste/principles.md), [components](../references/taste/components.md), [motion](../references/taste/motion.md) and [writing](../references/taste/writing.md) as the rule owners. If platform scope arises, native guidance is reported unavailable per setup.

## Define one thesis and build it small

State in one sentence what the user should feel and why that feeling belongs to this product. Then choose the smallest system that delivers it: a distinctive response to a meaningful action, product-specific language that clarifies while carrying voice, an interaction with recognizable material behavior, or a detail grounded in the product world that rewards discovery without hiding required functionality. Derive the treatment from the product mechanism and visual world, never a stock catalog.

Match the response to effort and consequence: major milestones may expand while routine saves simply feel certain. Show truthful progress during waiting with useful context; never fake work or delay completion to stage a flourish. Make the next action clear in empty and first-use states before adding personality. Lead errors with the problem and recovery; warmth may reduce stress but jokes must not trivialize loss, money, privacy or blocked work. Keep repeated interactions satisfying on the hundredth use, coherent and predictable enough to trust.

NEVER:

- Delay, block, or obscure the primary task for the flourish.
- Override platform conventions or accessibility.
- Add unrequested factual claims.
- Play sound without consent or ignore mute settings.
- Make the moment mandatory, unskippable, or exhausting on repeat.
- Add a dependency or asset cost disproportionate to the moment.
- Ship generic whimsy instead of the product's own language.

## Verify and finish

Build the change, inspect the moment on desktop and mobile widths where supported, fix observed defects in one batch, then perform at most one confirmation round. Where the change touches a local web file, one optional detector pass is allowed: `node {{PKG_DIR}}/scripts/detect.mjs --json <local-file>` on local files only, never URLs, web-only. A clean scan is not proof of design quality. Confirm muted, keyboard, touch and localized paths work where applicable; if browser or device verification is unavailable, mark those cases unverified.

Confirm the moment is specific enough that a neighboring product could not reuse it unchanged, that it improves comprehension, confidence, motivation or recovery, that the interface stays fast and obvious without the flourish, and that repetition does not turn charm into friction. Report what changed, concrete verification results, intentional exceptions and remaining limitations. Do not launch another capability or agent as an automatic finish handoff; naming `/impeccable polish` as a possible next step stays inline code, never an action.
