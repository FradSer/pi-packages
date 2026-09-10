# Capture durable product truth

Adapted from Impeccable `skill/reference/init.md` at `cd12f8660e2dde57b9615c8a6b8ea674101f9cfc`, Apache-2.0. Modified: removed launcher and platform-file handoffs so PRODUCT.md is written once then work resumes, replaced structured tool calls with conversation asks, dropped image-path and live-mode setup. See package licenses and notices.

`init` captures durable product truth in PRODUCT.md, once per project. It does not invent a visual world and does not write DESIGN.md. Recording the incumbent system happens later under `/impeccable document`; new surfaces are shaped later under `/impeccable shape`.

## Start from the resolved PRODUCT.md path

Resolve the PRODUCT.md path first and update it instead of creating a competing authority. In a child app inheriting root context, confirm shared versus app-specific scope before writing.

- **No PRODUCT.md:** explore, interview, and write it.
- **PRODUCT.md exists:** ask what product knowledge is stale or missing; do not reopen confirmed fields without a reason.
- **Legacy PRODUCT.md:** add only durable missing facts; absent `## Platform` means `web` unless evidence says otherwise.
- **Only DESIGN.md exists:** leave it untouched and create PRODUCT.md.
- **Redesign or rebrand request:** preserve confirmed product truth unless the user changes it. Visual replacement happens later, not here.

Never silently overwrite an existing file. If another request invoked init, finish PRODUCT.md and resume that request without rebuilding context.

## Explore before asking

Before asking, scan enough to avoid making the user repeat known facts: product docs and copy; package and config files and app boundaries; features, workflows, routes, and roles; names, logos, legal and proof assets, and brand commitments; platform and accessibility signals; and the dev command and entry point. Follow [target setup](setup.md) for the local project before drawing conclusions.

Treat repository evidence as a hypothesis, not user approval. Note visual maturity without documenting, extending, or replacing the world. Form a platform hypothesis of `web`, `ios`, `android`, or `adaptive` (one product that genuinely adapts its design language per operating system). Mobile web remains `web`; a wrapper around a website does not change its design language.

## Interview for product truth

There is no user-question tool: ask the user via conversation and proceed only on confirmation. Ask only about material gaps the repository and the original request do not answer with strong evidence. Keep rounds to at most three focused questions and require one real answer or approval round before writing a new PRODUCT.md. Confirm inferences rather than banking them.

Start with the unknowns that most change future product decisions: who the primary user is, in what situation, and what job they are doing; what the product makes possible and its meaningfully different mechanism or position; what durable constraints, assets, evidence, or product facts future work must preserve. Confirm an ambiguous platform separately. When the project has no framework or scaffold and the request implies building, the stack is a user decision, not yours: ask once whether they want plain static HTML and CSS, a specific framework, or your recommendation, plus any deploy target that constrains the answer, and record the outcome under `## Stack` (including `delegated` when they leave it to you). Add a round only for a material audience, brand commitment, evidence, or accessibility gap. Record undecided facts instead of inventing them.

Do not ask for an aesthetic direction, emotional feel, visual references, colors, typography, or style during init. If the user volunteers a binding visual constraint, record it without expanding it.

What belongs here: users, jobs, workflows, purpose, success, positioning, operating context, capabilities, constraints, terminology, evidence, platform, accessibility, and confirmed voice, assets, and brand commitments. What does not belong here: visual worlds, palettes, typography, components, page concepts, visitor mode, narrative, call-to-action or proof sequences, surface strategy, invented testimonials, customers, benchmarks, pricing, licensing, or deployment claims — and never a requirement to decide every optional field.

## Write PRODUCT.md

Write only confirmed facts and explicitly marked open decisions. Omit irrelevant sections rather than filling them with generic prose. New files go at the project root; otherwise update the resolved file.

```markdown
# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Stack
[Greenfield only: the answer to the stack question, or delegated with what was chosen and why. Omit when the codebase already answers it.]

## Users
[Primary users, their situation, and job. Add other audiences only when confirmed.]

## Product Purpose
[What the product does, why it exists, and what success means.]

## Positioning
[The mechanism or claim a neighboring product could not truthfully copy.]

## Operating Context
[Workflows, environments, tools, documents, materials, and rituals that are factual parts of using the product.]

## Capabilities and Constraints
[Confirmed functionality, technical constraints, terminology, and explicitly undecided product facts.]

## Brand Commitments
[Existing name, voice, assets, personality, identity constraints, and references the user made binding. Omit when none exist.]

## Evidence on Hand
[Real content, data, demonstrations, testimonials, case studies, press, or assets, with paths where applicable. State absences future work must not fabricate.]

## Product Principles
[Three to five durable strategic principles from confirmed answers; no visual recipes.]

## Accessibility & Inclusion
[Known user needs or required standard. Omit when no product-specific requirement was established.]
```

Platform is the bare value `web`, `ios`, `android`, or `adaptive`. Preserve useful legacy headings. Copy the schema comment verbatim; it records which version of the product record this file follows. Update its number only when this procedure's template changes it.

Before finishing, verify PRODUCT.md exists at the resolved path and contains the confirmed product record. If the file is absent, init is incomplete. Do not substitute interview notes or design prose for the file.

## Recommend next steps

Summarize captured and deliberately undecided facts. Do not offer DESIGN.md merely because it is missing. Recommend the next action from the actual project state, without rebuilding context: for an empty or early project, ask naturally for the surface to build, or use `/impeccable shape` when the user wants a confirmed brief without implementation; for a coherent interface without DESIGN.md, use `/impeccable document` if the user wants the incumbent system recorded; for an existing surface needing work, name the most relevant scoped command.

## Never

- Never silently overwrite an existing PRODUCT.md or DESIGN.md.
- Never invent a visual world, palette, typography, component, or page concept during init.
- Never ask for aesthetic direction, feel, references, colors, or type.
- Never invent testimonials, customers, benchmarks, pricing, licensing, or deployment claims.
- Never require every optional field to be decided before writing.
- Never launch another capability or agent as an automatic finish handoff.

## Report and stop

End with a short report: what was written, what was decided and what remains explicitly undecided, how PRODUCT.md was verified at its resolved path, and the limitations the next step must respect. Then stop.
