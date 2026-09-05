# Color

## Scope and measurement

Keep the project's notation, tokens and deliberate hierarchy. A consistent hex system is not defective because OKLCH exists. For a new system, OKLCH is useful for perceptual lightness/chroma/hue reasoning; exact conversions should use a color library, not estimates. Read the task boundary: reviewing a failing pair is not authorization to repaint it, and palette consolidation or bulk notation conversion requires an explicit request.

Measure foreground against the background actually behind it, including alpha, overlapping surfaces, images and gradients. Source values are evidence of declarations, not proof of which rule wins or what transparency composites to. Report the measured pair, method and applicable threshold; do not claim a contrast value from appearance. [Accessibility](accessibility.md#zoom-and-verification) decides which content and controls need the conformance check; this topic owns color computation and application.

## Ramps and roles

Most products need one neutral ramp, one accent and only the status ramps they render. A second accent must earn a distinguishable role, not multiply unused swatches. Neutral carries most surfaces and text; pure gray is valid, and subtly tinted neutral is a style choice. Keep a tint coherent, warm or cool, rather than accidentally mixing incompatible neutrals. The [image separator recipe](components.md#elevation-and-separators) is a scoped neutral exception, not a palette override.

Every step needs a consumed job. Tailwind's eleven50–950 steps describe lightness; Radix's twelve1–12 steps describe roles and reuse those roles in separate dark ramps. A light-mode mapping starts page50/1, subtle50/2, component100/3, hover200/4, active200/5, subtle border200/6, separator300/7, strong border400/8, solid500/9, solid-hover600/10, muted text700/11, strong text900/12. This is a role-planning aid, not proof a particular pair passes contrast. A twelve-role design may need distinct steps where Tailwind's mapping collides. Keep an existing scale and add the semantic seam rather than renumbering it for style.

Primitives describe hue/value; semantics describe the job and are what components consume. Surface, text, edge, accent and shipped status roles form an inventory checklist, not an obligation to instantiate unused tokens. Separate separator from enclosing border even if today's values match. A component-level token is justified for a genuine component exception, not as a default third layer everywhere.

Use one predictable naming grammar, such as --color-role-variant-state, while preserving established vocabulary. Do not mix foreground/text/ink for the same concept; reserve accent for brand when primary already means most prominent text. Never borrow a separator token as text merely because its value works today. In Tailwind v4, semantic --color-* entries in @theme become utilities; templates should use those role utilities, not bypass them with primitive colors.

## Generating and changing palettes

Before changing an existing system, inventory literals across CSS, utilities, SVG, charts and emails; group perceptually by hue/lightness, locate duplicates and assign consumed roles. Consolidate a confirmed near-duplicate by retaining the established usage, not averaging two arbitrary values. Present the proposed scope before repainting distant screens.

Start a new ramp from the brand's intended role. A contractually pinned brand color stays exact; build outward even if one step is uneven. Otherwise snapping to the planned scale may improve rhythm. If the brand cannot support the intended text contrast, keep its identity and choose a suitable other fill step rather than quietly darkening the contractual value.

Keep hue coherent, perceived lightness distinguishable, and chroma strongest in the middle and reduced toward extremes. Allocate finer light-background steps where roles need them; do not simultaneously demand mathematical equal spacing and denser light steps. Avoid identity-bearing ramps ending in pure black/white. Drop steps that render indistinguishably. Across status/accent hues, compare equal-role perceived lightness and relative chroma within each hue's achievable gamut, not identical saturation numbers.

Use an existing maintained library such as culori, colorjs.io or chroma.js for conversion, interpolation, gamut and measurement; inspect its actual APIs. A perceptual interpolation alone does not guarantee constant hue or a correct role ramp, so verify the output. Emit the project's existing notation. Convert only values in scope: keep keywords, comments, third-party expected formats and gradient interpolation intent intact.

## Meaning and emphasis

One hue family should have a coherent meaning; treat hues within roughly `15°` as potentially confusable, not as mathematically guaranteed perceptual equivalents. Where accent consistently means interactive, decorative accent text may invite dead clicks. Other established affordances can distinguish neutral interactive controls: do not recolor every button merely to enforce a slogan.

When filled color encodes primary emphasis, one primary action gets it and peer actions remain quieter. Distinct semantic states/categories can have multiple colored fills. Selected glyph/text is state, not necessarily competing primary emphasis. Status hues must distinguish destructive from primary actions, especially with a red brand. Verify side by side; moving red a few degrees is not proof the distinction is sufficient.

Locale can reverse conventions: Chinese financial displays often use red for gains and green for losses. Verify load-bearing meanings for the actual markets and model gain/loss by semantic locale-aware tokens. Do not substitute locale stereotypes for product research. [Redundant state cues](accessibility.md#announcements-and-persistent-state) remain mandatory regardless of hue.

## Contrast methods

For formal WCAG2.x checking, normal text uses AA `4.5:1` (AAA7:1); large text AA3:1 (AAA4.5:1). Large means at least18pt, approximately `24px`, or14pt bold, approximately18.67px; do not round downward to incorrectly exempt borderline text. Applicable non-text components/graphics use3:1. These are measurement thresholds applied under the accessibility owner's scope and exceptions, not a claim every decoration needs them.

APCA can provide additional design guidance, not replace the project's WCAG conformance gate. Its signed Lc preserves polarity; compare magnitude for the selected recommendation. Source shorthand targets are body75(preferred90), other text60(preferred75), large36px+45(preferred60), component30. Full APCA guidance depends on font size/weight and version; use the actual method's tables rather than treating this shorthand as law. Disabled and placeholder advisory targets are not new WCAG requirements.

Change lightness first for a requested contrast repair, holding hue where possible and reducing chroma if gamut requires. A middle-lightness background may be the limiting factor, so changing foreground alone is not always enough. Remeasure both appearances. Do not copy upstream illustrative Lc values as measurements of the target project. WCAG ratio is symmetric under swapping an opaque pair; APCA and actual themed/translucent pairs need not be. Do not generalize polarity-dependent behavior to every contrast algorithm.

## Gamut gradients and themes

Generate for supported displays, usually sRGB, with P3 as an explicit enhancement. Reduce chroma while retaining intended lightness/hue when a color exceeds gamut; inspect whether adjacent steps collapse. Declare an sRGB fallback and override inside color-gamut:p3 where that enhancement is intended. Older syntax support may need @supports, but do not add dead fallbacks without a browser requirement. Out-of-gamut colors are mapped by browsers; absence of a P3 fallback is a rendering-risk assessment, not automatically proof all pixels disappear.

Gradient interpolation is a look: oklab is a useful even-looking default; polar oklch traverses hue and can avoid a gray midpoint, but may introduce unexpected hues; existing sRGB may intentionally give a darker/muted middle. Opposing hues can pass near neutral in a rectangular space; use a third stop or choose the polar path deliberately. Shorter/longer hue selects route, not quality. Check banding on large regions; subtle noise, a smaller area or altered stops may help. Text over a gradient needs worst-region checking or a sufficiently opaque scrim, not an average sample.

Dark appearance is not mechanical reversal. Repoint roles, then tune chroma and surface separation and verify rendered pairs again. Prefer one switching mechanism: OS media query alone without an override; a class/attribute with a system-derived initial choice when users override; light-dark only when color-scheme is correctly managed. A class named dark is not technically required if the project uses another deliberate mechanism.

Respect [reduced transparency and increased contrast](accessibility.md#reduced-motion). Increased-contrast appearances need measured stronger differentiation; an advisory15-point perceived-lightness gap increase is not a substitute for testing. Relative colors, color-mix and alpha can derive useful states, but chained token derivations obscure intent. Resolve the actual inputs/result before checking; a literal declaration alone may not tell the whole rendered story. Theme-switch motion has its single owner in [motion](motion.md#performance).

## Verification

Check actual light/dark/increased-contrast appearances, worst backgrounds, semantic collisions, locale meaning, gamut and role-token usage. Report pair measurements and the limits of source-only checks. Apply color changes only within the requested scope, then remeasure; never convert an entire notation system as incidental polish.
