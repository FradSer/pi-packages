# Technical audit with scored report

Adapted from Impeccable `skill/reference/audit.md` at `cd12f8660e2dde57b9615c8a6b8ea674101f9cfc`, Apache-2.0. Modified: Pi-native static detector path, native platforms reported unavailable instead of a native supplement, no browser or network steps. See package licenses and notices.

Audit measures; it does not fix. Run the checks, score each dimension, document issues for other commands to address.

## Checks

Follow [target setup](setup.md). Score each dimension 0-4 against [accessibility](../references/taste/accessibility.md), [principles](../references/taste/principles.md), and [components](../references/taste/components.md):

1. **Accessibility**: contrast below 4.5:1, missing `prefers-reduced-motion` alternatives, missing ARIA roles/labels/states, keyboard traps or invisible focus, broken heading/landmark structure, missing alt text, unlabeled inputs and poor error messaging. 0 fails WCAG A; 4 meets AA throughout, approaching AAA.
2. **Performance**: layout thrash in loops, layout-property animation and unbounded blur/filter/shadow, images without lazy loading, broad or resting `will-change`, unused imports and dependencies, unmemoized re-renders. 0 systemic; 4 fast and lean.
3. **Theming**: hard-coded colors outside tokens, broken or low-contrast dark mode, mixed token types, values that ignore theme switching. 0 no tokens; 4 full token system with working dark mode.
4. **Responsive**: fixed widths that break narrow viewports, touch targets under 44px, horizontal overflow, layouts that break under text scaling, missing breakpoints. 0 desktop-only; 4 fluid everywhere.
5. **Implementation integrity**: run the packaged detector once over local markup, `node "{{PKG_DIR}}/scripts/detect.mjs" --json "<local-file>"` (local files only, never URLs; web-only; exit 2 primary findings, 0 clean or advisory-only), verify every finding in context, and judge whether the code expresses one coherent product system. Keep deterministic findings separate from visual taste and call out false positives. 0 systemic drift; 4 coherent and intentional.

Native platforms (`ios`, `android`, `adaptive`) have no packaged supplement: report that explicitly and audit only the shared, platform-neutral source; never substitute web measurements for native ones.

## Report

**Audit Health Score ??/20** with per-dimension rows (score plus key finding). Bands: 18-20 Excellent, 14-17 Good, 10-13 Acceptable, 6-9 Poor, 0-5 Critical. Then an integrity verdict (pass/fail with verified evidence), an executive summary (score, counts by severity, top 3-5 critical issues, next steps), detailed findings each tagged **P0 Blocking** (prevents task completion), **P1 Major** (serious difficulty or WCAG AA violation), **P2 Minor** (annoyance with workaround), or **P3 Polish** (no real user impact) with location, category, user impact, violated standard, recommendation, and suggested command, plus systemic patterns and positive findings worth replicating. Be thorough but actionable: too many P3s is noise, every issue needs its impact, no generic advice, nothing unprioritized, no unverified finding presented as fact.

List Recommended Actions in priority order from `/impeccable adapt`, `animate`, `audit`, `bolder`, `clarify`, `colorize`, `critique`, `delight`, `distill`, `document`, `harden`, `layout`, `onboard`, `optimize`, `overdrive`, `polish`, `quieter`, `shape`, `typeset`, ending with `/impeccable polish` when fixes were recommended. Then tell the user: run these one at a time, all at once, or in any order; re-run `/impeccable audit` after fixes to see the score improve. That score is the top-score definition: fixes land only through the recommended commands, verified by at most one confirmation round each, never an open-ended loop.
