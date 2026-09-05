# Typography

## Fonts and loading

Keep the product's type family unless changing it is requested. A commercial or proprietary face is a licensing and brand decision, never a checklist dependency. For a new neutral interface, a system font stack is a useful default; expressive editorial/display choices need a purpose. Usually no more than three families are needed. Pair contrast, such as serif display with sans body, rather than nearly identical families.

Use WOFF2 for web delivery; add WOFF only for an actual old-browser requirement. Do not casually deliver raw desktop TTF/OTF when compressed web files exist. A family named Display may have a Text companion: choose the optical variant for the rendered size, not the name's apparent prestige. A font's x-height, cap height and apertures explain why equal CSS sizes need not look equal.

Load the real weights and styles in use. A variable file can be economical across many weights or optical sizes, but one or two static faces may be smaller. Keep fallback emphasis distinguishable. `font-synthesis: none` disables several synthesized forms and can erase bold/italic distinctions; use only after verifying the required forms across the fallback stack, or disable just the verified synthesis mode.

## Scale and spacing

Use the established scale with clear roles. A new interface can begin with display `2.25rem/1.1/600`, title `1.5rem/1.2/600`, heading `1.125rem/1.3/600`, body `1rem/1.5/400`, caption `0.8125rem/1.4/400` (size/line-height/weight). These are scoped starting values, not mandatory replacements. Semantic role names help teams use a size consistently; generic framework names work when usage is clear. Emphasize within a role with one weight step, not an unrelated size.

Make visual heading hierarchy descend; adjacent deep levels can share size when weight/spacing distinguishes them. Heading tags follow [document semantics](accessibility.md#semantics-and-names), never browser-default appearance. A deliberately subordinate overline may be smaller than body text.

Short headings can use roughly `1.1` line-height; reading body uses `1.5–1.6`. Text wrapping to three or more lines needs at least `1.4`, even in compact rows. Use unitless line-height so it follows font size. Large headings may tighten tracking (`-0.02em` as a starting point); small uppercase labels may loosen it (`0.05em`); ordinary body stays near zero. Do not apply one tracking value to all sizes or scripts. Tall scripts need room, not clipped ascenders.

Below `18px`, prefer weight `400` or heavier. Thin/light treatment belongs to display at `28px` or larger and still needs visual checking. Long-form body starts around `16px`; dense UI may justify smaller text, with inputs/menus around `14px`, captions `13px`, and rarely below `12px`. These are readability judgments, not universal WCAG font-size rules.

For long-form measure, target `60–75` characters per line. `65ch` is a useful proxy, not an exact character counter (`ch` is the width of zero). At `16px` body, roughly `560–680px` can fit that range depending on the face; verify after font changes. Use the project's units consistently; let text and layout respond to the reader's settings.

## Font features

Prefer CSS properties over raw OpenType tags: `font-weight: 650`, `font-optical-sizing: auto`, `font-variant-numeric: tabular-nums` and `slashed-zero`. These express intent and preserve useful fallback behavior. Reserve font-variation-settings for supported custom axes such as GRAD, and font-feature-settings for niche features such as ss01 or cv11. Axis and feature availability is font-file-specific, so inspect its documentation; a tag's numbered meaning is not portable across families.

Real small caps use font-variant-caps; real super/subscripts use font-variant-position when the font provides them. Do not silently fake missing forms. Kerning is normally built into the face; disable it only deliberately.

Text-box trimming can align badge/header glyphs optically (`text-box: trim-both cap alphabetic`), but treat it as progressive enhancement after checking the supported browser matrix and scripts. Unsupported browsers must retain usable ordinary leading. Root-level font smoothing can be part of the established macOS treatment; it is not a guarantee that every font otherwise renders incorrectly. Avoid per-component smoothing inconsistencies.

## Wrapping and truncation

Use text-wrap balance on short headings, pretty on descriptions, and ordinary wrapping for long-form passages. Allow long URLs and identifiers to break before escaping their container. Keep a label unbroken only where it still fits translated content; nowrap is not permission to clip it. Prefer start alignment; justification belongs to selected editorial contexts, not routine controls.

Single-line ellipsis needs overflow hidden and nowrap; multiline clamping also hides content. If the missing value matters, make it available through an accessible expanded view or tooltip that works beyond hover. Test real longest strings and the narrowest actual container. The [layout](layout.md#disclosure-and-adaptation) owns room and disclosure; this section owns text behavior.

Store natural-case copy and use CSS for presentation. Use curly quotes in prose, straight quotes in code, en dashes in ranges, a single ellipsis character, nonbreaking spaces for values and units, and discretionary soft hyphens only where sensible. Language-aware typography must not rewrite technical identifiers.

## Numbers and direction

Changing timers, counters, prices and aligned numeric columns use tabular figures so glyph widths do not make the layout wobble. Slashed zero can distinguish identifiers when the font supports it. These features do not require a number-animation library.

Set lang for pronunciation, hyphenation and quotation conventions; set dir at the content boundary. Long paragraphs (three or more lines) should align to their own script rather than blindly inherit the surrounding UI direction. Keep digit order intact, and isolate mixed-direction values with `<bdi>` when adjacent text disturbs their ordering. Spatial mirroring belongs to [layout](layout.md#alignment-and-order).

## Editable and interactive text

iOS Safari may zoom inputs with text below `16px`. Prefer an actually readable `16px` mobile input and the project's smaller desktop size when appropriate. An explicitly requested visually smaller alternative keeps computed font-size at16px and scales the input with compensation: for13px, scale `0.8125`, width `100% / 0.8125`, and line-height divided by `0.8125`. Put surface/border on an unscaled wrapper and match transform-origin to direction. This is a design tradeoff, not a way to disable zoom; do not silently select the smaller-looking route. Verify hit area, focus, caret, selection and readability. The [form semantics](accessibility.md#forms-and-disabled-states) remain unchanged.

Keep useful text selectable. Suppress selection only where it demonstrably conflicts with a drag/gesture, not across all chrome. Selection colors must remain legible. Caret-color and placeholder styling can follow the system; a custom caret rarely earns its complexity.

Use underline position/thickness from the font where appropriate, then tune offset and skip-ink. A dotted underline can signal extra information. For animation beyond underline color, use a separate decorative element rather than assuming all text-decoration geometry interpolates reliably. Custom Highlight API and target-text can decorate ranges without replacing semantic text; check browser support before depending on them.

## Verification

Read rendered content at real lengths, not just CSS declarations. Check loaded/fallback fonts, emphasis, descending heading treatment, measure, multi-line leading, punctuation, mixed scripts, tabular figures, truncation access and mobile input behavior. [Zoom and contrast constraints](accessibility.md#zoom-and-verification) stay in the accessibility owner. Report unsupported-browser and font-file assumptions rather than claiming every feature works from its CSS name alone.
