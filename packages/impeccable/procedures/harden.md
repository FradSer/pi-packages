# Harden the interface against reality

Adapted from Impeccable `skill/reference/harden.md` at `cd12f8660e2dde57b9615c8a6b8ea674101f9cfc`, Apache-2.0. Modified: Pi tool boundaries, manual static detection and bounded verification replace upstream handoffs. See package licenses and notices.

Designs that only work with perfect data are not production-ready. Harden the requested scope against extreme inputs, failure states, language expansion and adverse network conditions. Preserve the incumbent visual world, factual copy and behavior; report conceptual mismatches separately rather than redesigning under the name of hardening.

## Establish scope and evidence

Follow [target setup](setup.md). Run `node {{PKG_DIR}}/scripts/context.mjs`, adding `--target <path>` when the user names one. Inspect the whole requested path, not just its happy state. Use existing product context and representative shared components to distinguish a local defect, a missing reusable token and a genuinely uncovered edge case. Fix the cause at the narrowest correct level; do not invent abstractions for a single exception.

Use [principles](../references/taste/principles.md) and [components](../references/taste/components.md) as the rule owners. Inspect text handling, error design and empty, loading, permission and failure states against the actual project system; disclose missing specialized guidance rather than claiming coverage from this procedure alone.

## Harden systematically

Exercise extremes where available: very long, very short and empty text; special characters and emoji; very large numbers; very long lists and option sets; no data at all. Confirm containers expand, text truncates or wraps deliberately, and flex and grid items cannot overflow their bounds. Never use fixed widths for text containers; budget 30-40 percent expansion for translation and keep the English-length layout from passing as global-ready.

Cover failure honestly: offline, slow and timed-out networks; validation, permission and rate-limit errors; one failing component must not take down the whole interface. Show a specific message, preserve user input, and offer the narrowest recovery such as retry. Validate every input on the client for speed and on the server for safety; never trust client-side validation alone and never leave a bare generic error.

Respect language and input breadth: expanded translations, right-to-left layout through logical properties, CJK and emoji character sets, and locale-correct dates, numbers and currency. Keep keyboard order, focus management, names and labels intact under every hardened state.

NEVER: assume perfect input; ignore internationalization; leave generic error messages; forget offline and slow-network cases; trust client-side validation alone; use fixed widths for text; assume English-length text; block the entire interface when one component errors.

## Verify and finish

Build the scoped change, exercise the extreme, error and empty cases together, fix observed defects in one batch, then perform at most one confirmation round. Follow setup's explicit local detector path once where supported: run `node {{PKG_DIR}}/scripts/detect.mjs --json <local-file>` against local files only, never URLs, web-only; a clean scan is not proof of resilience. If browser, device or throttled-network verification is unavailable, mark those cases unverified rather than pretending a source review exercised them.

Review the source diff for accidental churn, dead code, duplicated styles and temporary artifacts. Report what changed, concrete verification results, intentional exceptions and remaining limitations. Do not launch another capability or agent as an automatic finish handoff.
