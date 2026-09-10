# Record the incumbent visual system

Adapted from Impeccable `skill/reference/document.md` at `cd12f8660e2dde57b9615c8a6b8ea674101f9cfc`, Apache-2.0. Modified: condensed the extraction and seed flows to Pi boundaries, replaced structured tool calls with conversation asks, trimmed the sidecar schema to extension-only essentials. See package licenses and notices.

Document records the incumbent visual system in DESIGN.md at the project root, so future screens stay on-brand. The YAML frontmatter carries machine-readable tokens and is normative; the prose gives context for applying them. Use the eight canonical sections in fixed order and omit irrelevant ones rather than filling them with invented rules: Overview, Colors, Typography, Layout, Elevation and Depth, Shapes, Components, Do's and Don'ts. Keep exact headings and exact section names so tooling keeps parsing.

## When to run

Run document when a coherent incumbent system exists without DESIGN.md; when the first implementation of a new world is complete and its provisional decisions need carbonizing; when an existing DESIGN.md has drifted stale; or before a large redesign, to capture current state as reference.

If DESIGN.md already exists, do not silently overwrite it. Show the user the existing file first, then ask the user via conversation and proceed only on confirmation. The choice is refresh, overwrite, or merge. There is no user-question tool; conversation approval is the gate.

## Choose scan or seed

Scan mode is the default: the project has tokens, components, or rendered output to extract. Seed mode is for pre-implementation projects with no visual system yet. Decide by scanning first. If the scan finds no tokens, no component files, and no rendered output, offer seed mode; do not silently switch. A seed request never authorizes replacing coherent code: when an incumbent system exists, offer scan mode instead.

## Scan mode: auto-extract, then confirm descriptive language

Step 1 is finding the design assets, in priority order: CSS custom properties for color, font, spacing, radius, shadow, easing, and duration (record name, value, and defining file); the Tailwind config theme extension for colors, font family, spacing, radius, and shadow; theme or token files such as theme, tokens, or Style Dictionary output; the component library, noting variant APIs and default styles of button, card, input, navigation, and dialog; the global stylesheet for base typography and color assignments; and rendered output where available, sampling computed styles of body, headings, links, buttons, and cards to catch values tokens miss.

Step 2 is auto-extracting the checklist from what was found. Colors group into Primary, Secondary, Tertiary, and Neutral; with a single accent, express Primary plus Neutral and omit the rest rather than inventing them. Typography maps observed sizes and weights to display, headline, title, body, and label, noting family stacks and scale ratio. Spacing and layout cover grid, container, breakpoint, rhythm, and density. Radii cover corner strategy, borders, clipping, and recurring form behavior. Elevation catalogues the shadow vocabulary, or states flat tonal layering explicitly. Component patterns cover shape, color assignment, hover and focus treatment, and internal padding for button, card, input, chip, list item, tooltip, and navigation.

Step 3 is staging the frontmatter from the extracted tokens:

```yaml
---
name: <project title>
description: <one-line tagline>
colors:
  primary: "#b8422e"
  neutral-bg: "#faf7f2"
typography:
  display:
    fontFamily: "Georgia, serif"
    fontSize: "clamp(2.5rem, 7vw, 4.5rem)"
    fontWeight: 300
    lineHeight: 1
rounded:
  sm: "4px"
  md: "8px"
spacing:
  sm: "8px"
  md: "16px"
components:
  button-primary:
    backgroundColor: "{colors.primary}"
    textColor: "{colors.neutral-bg}"
    rounded: "{rounded.sm}"
    padding: "16px 48px"
---
```

Token references use brace paths such as `{colors.primary}`; components may reference primitives, primitives never reference each other. Colors accept any valid CSS string but keep the project's canonical format; never split the source of truth. Component sub-tokens are limited to backgroundColor, textColor, typography, rounded, padding, size, height, and width; shadows, motion, focus rings, and backdrop treatments ride in the sidecar. Scale keys and color slugs use the project's own names. Variants are sibling keys by naming convention. Skip anything the project does not have; fabricated tokens pollute the file, and no token group outside colors, typography, rounded, spacing, and components belongs in frontmatter.

Step 4 is asking the user for the descriptive language that cannot be extracted: the creative North Star (one named metaphor, with two or three options honoring confirmed brand personality); the overview voice (mood, philosophy in two or three sentences, any confirmed visual anti-reference); color character (descriptive names per key color, with two or three suggestions each); the elevation philosophy (flat, layered, or lifted; ambient or structural shadows); and the component feel in one phrase. Ask in at most two rounds of three questions, wait between rounds, and proceed only on confirmation. Carry a PRODUCT.md line only when it is a durable brand commitment that constrains the visual system.

Step 5 is writing DESIGN.md: the staged frontmatter first, then the body. Overview opens with the North Star line, then personality, density, and philosophy in two or three paragraphs, ending in a Key Characteristics list. Colors describe palette character in one sentence, then Primary, Secondary, Tertiary, and Neutral entries with descriptive names, exact values in parens, and where and why each is used; add short named rules for hard doctrines. Typography names the display, body, and label fonts with fallbacks, one or two sentences of character, then the display-to-label hierarchy with weight, size, and line height plus purpose. Layout describes grid, container, density, responsive changes, and spacing rhythm with exact values only when observed. Elevation and Depth states the depth model in one paragraph (flat systems say so and describe the tonal substitute) with a shadow vocabulary when shadows exist. Shapes describes corners, borders, clipping, and recurring silhouette. Components lead each entry with a character line, then shape, color assignment, states, and distinctive behavior for buttons, chips, cards, inputs, navigation, and any signature component. Do's and Don'ts gives concrete guardrails grounded in the implementation, each leading with Do or Don't and exact values only when established.

Alongside DESIGN.md, write the `.impeccable/design.json` sidecar carrying what frontmatter cannot hold: tonal ramps per color (eight steps, dark to light, reusing project scales where they exist), shadow, motion, and breakpoint tokens, full component snippets, and the narrative. Regenerate it whenever DESIGN.md regenerates. Keep five to ten components that best represent the system: canonical primitives first (button variants as separate entries, input, navigation, chip, card), then signature patterns, skipping the rest; where no library exists yet, synthesize primitives from the tokens consistent with the stated rules. Each snippet must be self-contained: expand utilities to literal CSS, reference root custom properties only where they exist, inline icons as SVG, include hover and focus-visible rules, skip universal resets, and prefix classes so entries do not collide. Pull narrative fields (North Star, overview, key characteristics, named rules, dos, donts) verbatim from DESIGN.md without rewording.

Step 6 is confirmation: show the full DESIGN.md, highlight the non-obvious creative choices (descriptive color names, atmosphere language, named rules), note the sidecar was written alongside, and offer one refinement round for missed patterns or adjusted language.

## Seed mode: commit a direction, not tokens

Seed mode is for projects with no visual system to extract. It produces a user-chosen scaffold, not a fabricated token spec. PRODUCT.md is the prerequisite: when it is missing, complete the product interview through conversation first and never create an identity without durable product context. Establish the direction with the user against a concrete first surface (the named target, or ask what to make first), choosing palette strategy, type character, spatial grammar, material behavior, form language, and durable guardrails together. Then write the seed DESIGN.md in canonical section order, leading the file with a seed marker comment stating it was established with the user before implementation and must be re-run once code exists. Include values only when the user, an existing asset, or the workshop established them; mark everything else as to-be-resolved during implementation. Omit Components entirely and write minimal frontmatter with name and description only. Skip the sidecar: there is nothing to render yet. Show the seed file, call out its seed status, and tell the user to re-run `/impeccable document` once code exists so the scan pass extracts real tokens and generates the sidecar.

## Never

- Never silently overwrite, refresh, or merge an existing DESIGN.md without explicit confirmation.
- Never invent tokens, components, testimonials, or rules the code and the user did not establish.
- Never paste raw class names as documentation; translate to descriptive language with exact values in parens.
- Never rename canonical sections or add token groups the schema does not support.
- Never duplicate token values between frontmatter and prose; frontmatter is normative.
- Never launch another capability or agent as an automatic finish handoff.

## Report and stop

End with a short report: what was written, what was decided and what remains explicitly undecided, how the file was verified against the codebase and the user's confirmations, and the limitations the next step must respect. Then stop.
