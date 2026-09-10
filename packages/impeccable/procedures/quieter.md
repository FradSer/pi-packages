# Make a loud design quieter

Adapted from Impeccable `skill/reference/quieter.md` at `cd12f8660e2dde57b9615c8a6b8ea674101f9cfc`, Apache-2.0. Modified: Pi tool boundaries replace upstream handoffs, manual clarification and bounded verification replace upstream question-tool and polish-handoff automation. See package licenses and notices.

Quiet design is harder than bold design. Subtlety needs precision. Reduce visual intensity in work that is too loud, aggressive, or overstimulating without losing personality or collapsing into generic gray. Quieter means refined and easier on the eyes, never boring.

## Establish scope and evidence

Follow [target setup](setup.md). Run `node {{PKG_DIR}}/scripts/context.mjs`, adding `--target <path>` when the user names one, and inspect the whole requested surface before cutting anything. Distinguish the purpose from the noise: a persuasion surface keeps its point of view with a more restrained palette, more whitespace and more typographic air, drama reduced but not eliminated; a tool or reading surface disappears more completely into the task with fewer accents, flatter cards, less color and less motion.

Use [principles](../references/taste/principles.md), [components](../references/taste/components.md), [color](../references/taste/color.md), [typography](../references/taste/typography.md), [layout](../references/taste/layout.md) and [motion](../references/taste/motion.md) as the rule owners. If platform scope arises, native guidance is reported unavailable per setup.

## Assess what makes it intense

Name the intensity sources before changing anything: oversaturated color, contrast extremes, too many heavy elements competing, excess or dramatic motion, decorative complexity, or scale with no hierarchy. Record what is working, who the surface serves, and what the core message is; preserve what matters and do not throw away good ideas with the noise. If the purpose, audience, or core message cannot be inferred from the target and context, stop and ask the user rather than guessing.

Plan the refinement as an explicit strategy: the color approach (desaturate, restrain, reduce variety, let neutrals carry the surface with color as a small accent), the hierarchy approach (which very few elements stay bold, which recede), the simplification approach (what is removed entirely), and the sophistication approach (how restraint signals quality). Subtlety without intent collapses to generic.

## Refine with restraint

Reduce saturation toward muted tones, narrow the palette, and reserve high contrast for what matters most. Prefer tinted grays over pure gray for depth without loudness. Reduce font weights and sizes where appropriate and build hierarchy through weight, size and space instead of color and loudness. Increase breathing room, thin or remove borders and lines, and strip gradients, shadows, patterns and glows that serve no purpose. Simplify extreme radii and custom shapes, flatten needless layering. Shorten motion distances, keep functional motion, remove flourishes, and remove animation entirely where it serves no clear purpose.

NEVER:

- Flatten everything to one size and weight; hierarchy still matters.
- Remove all color; quiet is not grayscale.
- Eliminate all personality; maintain character through refinement.
- Sacrifice usability for aesthetics; functional elements keep clear affordances.
- Make everything small and light; keep anchors the eye can hold.

## Verify and finish

Build the change, inspect the surface on desktop and mobile widths where supported, fix observed defects in one batch, then perform at most one confirmation round. Where the change touches a local web file, one optional detector pass is allowed: `node {{PKG_DIR}}/scripts/detect.mjs --json <local-file>` on local files only, never URLs, web-only. A clean scan is not proof of design quality. If browser or device verification is unavailable, mark those cases unverified.

Confirm users can still complete tasks, the surface is still distinctive, extended reading is easier, and the point of view survived the cuts. Report what changed, concrete verification results, intentional exceptions and remaining limitations. Do not launch another capability or agent as an automatic finish handoff; naming `/impeccable polish` as a possible next step stays inline code, never an action.
