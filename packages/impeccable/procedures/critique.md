# UX design critique with heuristic scoring

Adapted from Impeccable `skill/reference/critique.md` at `cd12f8660e2dde57b9615c8a6b8ea674101f9cfc`, Apache-2.0. Modified: sequential inline assessments (Pi authorizes no sub-agent tools), static-detector evidence instead of browser injection, report-embedded snapshot instead of storage CLI, conversation questions instead of a dedicated question tool. See package licenses and notices.

Critique evaluates; it does not fix. Assess first, report fully, then ask the user what to improve. The chat response is the deliverable.

## Setup

Follow [target setup](setup.md). Resolve the target to a concrete source path; prefer paths over URLs, never invent product truth. Read `<project>/.impeccable/critique/ignore.md` when it exists and drop matching findings silently.

## Assessment A: design review

Inspect the source and judge like a design director, before any detector output enters synthesis:

- **Design specificity**: is the composition grounded in this product, or interchangeable with an unrelated one? Judge this first.
- **Holistic pass**: hierarchy, IA, emotional fit, discoverability, composition, typography, color, [accessibility](../references/taste/accessibility.md), states, copy, edge cases, against [principles](../references/taste/principles.md) and [components](../references/taste/components.md).
- **Cognitive load**: fail count over the 8 checks below. 0-1 low, 2-3 moderate, 4+ high (critical).
  1. Single focus on the primary task; 2. chunking (4 or fewer items per group); 3. related items grouped; 4. obvious visual hierarchy; 5. one decision at a time; 6. 4 or fewer visible options per decision (working-memory limit); 7. no memory bridge across screens; 8. progressive disclosure. Common violations: wall of options, hidden navigation, jargon, uniform visual weight, inconsistent patterns, multi-task demand, context switches.
- **Emotional journey**: peak-end fit, valleys, reassurance at high-stakes moments.
- **Nielsen heuristics 0-4** (4 is genuinely excellent; most real interfaces land 20-32/40): 1. system status feedback; 2. match with the real world; 3. user control and exits; 4. consistency; 5. error prevention; 6. recognition over recall; 7. flexibility and shortcuts (`n/a` allowed on Persuade/Experience surfaces); 8. minimalist aesthetics; 9. error diagnosis and recovery; 10. help and docs (`n/a` allowed on Persuade/Experience surfaces). Renormalize the maximum when heuristics are `n/a` (4 per scored heuristic) and record which were skipped. Bands by percentage: 90+ Excellent, 70+ Good, 50+ Acceptable, 30+ Poor, below Critical.
- **Personas**: walk the primary action as 2-3 of Alex (impatient power user: shortcuts, skip, under 60 seconds), Jordan (first-timer: labeled icons, plain language, clear first action in 5 seconds), Sam (screen reader/keyboard-only: focus, labels, 4.5:1 contrast, no color-only meaning), Riley (stress tester: empty states, long input, refresh mid-flow), Casey (distracted mobile: thumb zone, state persistence, 44px targets). Landing: Jordan/Riley/Casey. Dashboard: Alex/Sam. Checkout: Casey/Riley/Jordan. Onboarding: Jordan/Casey. Data-heavy: Alex/Sam. Form-heavy: Jordan/Sam/Casey. Report concrete red flags per persona, never generic descriptions.

## Assessment B: static evidence

Run the packaged static detector once over local markup: `node "{{PKG_DIR}}/scripts/detect.mjs" --json "<local-file>"` (local files only, never URLs; exit 2 means primary findings, 0 clean or advisory-only). Verify each finding in context and flag false positives. Browser inspection, overlays, and live injection are unavailable in Pi; report them as skipped with that reason rather than substituting source guesses for rendered evidence.

## Report

First line declares the method: `Method: single-context (sequential A then B; Pi authorizes no sub-agent tools)`. Then, woven together (never concatenated), detector agreements, misses, and false positives included:

1. **Design Health Score** table (10 heuristics, score, key issue) with renormalized total and band.
2. **Design Specificity Verdict** first among prose: authored for this product or category-interchangeable, with deterministic-scan counts and locations.
3. **Overall impression**: gut reaction plus the single biggest opportunity.
4. **What's working**: 2-3 specific strengths.
5. **Priority issues** (3-5, ordered): each with P0 Blocking / P1 Major / P2 Minor / P3 Polish severity, why it matters to users, a concrete fix, and a suggested command (`/impeccable adapt`, `animate`, `audit`, `bolder`, `clarify`, `colorize`, `delight`, `distill`, `document`, `harden`, `layout`, `onboard`, `optimize`, `overdrive`, `polish`, `quieter`, `shape`, `typeset`).
6. **Persona red flags**, **minor observations**, **provocative questions to consider**.
7. **Snapshot**: repeat the score table, verdict, and priority issues as one archive block. There is no trend storage; `/impeccable polish` inherits priorities from this report, not from disk.

## Close

End the response with 2-4 targeted questions carrying 2-3 concrete options each (priority direction, design intent, scope, constraints only when relevant), report first and questions last. With fewer than 3 priority issues questions may be skipped, printing the literal line `Questions skipped: <reason>`; otherwise ending without questions is an incomplete run. After answers arrive, present prioritized Recommended Actions mapped to real issues, ending with `/impeccable polish` when fixes were recommended: run items one at a time, all at once, or in any order, then re-run `/impeccable critique` to see the score improve.
