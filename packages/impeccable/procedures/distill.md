# Strip a design to its essence

Adapted from Impeccable `skill/reference/distill.md` at `cd12f8660e2dde57b9615c8a6b8ea674101f9cfc`, Apache-2.0. Modified: Pi tool boundaries replace upstream handoffs, manual clarification and bounded verification replace upstream question-tool and polish-handoff automation. See package licenses and notices.

Distill by removing what does not earn its place: redundant elements, repeated information, decorative noise and cosmetic complexity. Simplicity is not fewer features; it is fewer obstacles between users and their goals. Every remaining element should justify its existence.

## Establish scope and evidence

Follow [target setup](setup.md). Run `node {{PKG_DIR}}/scripts/context.mjs`, adding `--target <path>` when the user names one, and inspect the whole requested surface before cutting. Name the complexity sources: competing actions, purposeless variation in color and type, everything visible at once, borders and containers that carry no hierarchy, unclear priority, or options that accumulated past the task. Then find the essence: the one primary user goal, what is necessary versus nice to have, what can be removed, hidden or combined, and the small share that delivers most of the value.

Use [principles](../references/taste/principles.md), [components](../references/taste/components.md), [layout](../references/taste/layout.md), [typography](../references/taste/typography.md) and [writing](../references/taste/writing.md) as the rule owners; color tokens stay as the project defines them. If platform scope arises, native guidance is reported unavailable per setup.

If the primary goal, the necessary set, or the consolidation target cannot be inferred from the target and context, stop and ask the user rather than guessing. Plan the cut explicitly: the one purpose the surface must accomplish, the essential elements, what hides behind progressive disclosure until needed, and what combines into fewer actions and clearer hierarchy.

## Simplify across dimensions

Reduce scope to one primary action with few secondary ones; hide the rest behind clear entry points and remove what is said elsewhere. Narrow the palette, limit type to one family with few sizes and weights, remove decorations that serve no hierarchy, flatten needless nesting, and never nest cards inside cards; prefer spacing and alignment over containers for basic layout. Replace complex grids with simple flow where the task allows, keep one alignment and one spacing scale, and let content breathe.

Cut choices to the clearest path forward with smart defaults, shorten flows, and make the one next action obvious. Cut copy hard toward short active sentences in plain language with scannable structure, saying each thing once. Remove dead styles, unused components and needless variants in the touched code only; do not redesign outside the requested scope.

NEVER:

- Remove functionality users need to complete the task.
- Sacrifice accessibility for simplicity; labels and semantics stay.
- Make the result mysterious; minimal must stay clear.
- Remove information users need to decide.
- Eliminate hierarchy completely; some things must stand out.
- Force simple treatment onto a domain whose task is genuinely complex.

## Verify and finish

Build the change, inspect the surface on desktop and mobile widths where supported, fix observed defects in one batch, then perform at most one confirmation round. Where the change touches a local web file, one optional detector pass is allowed: `node {{PKG_DIR}}/scripts/detect.mjs --json <local-file>` on local files only, never URLs, web-only. A clean scan is not proof of design quality. If browser or device verification is unavailable, mark those cases unverified.

Confirm faster task completion, lower cognitive load, intact necessary features, clearer hierarchy and no accidental churn in the diff. Document removed features or options with why they were removed and any alternative access point worth monitoring. Report what changed, concrete verification results, intentional exceptions and remaining limitations. Do not launch another capability or agent as an automatic finish handoff; naming `/impeccable polish` as a possible next step stays inline code, never an action.
