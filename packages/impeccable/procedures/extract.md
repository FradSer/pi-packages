# Extract what is clearly reusable now

Adapted from Impeccable `skill/reference/extract.md` at `cd12f8660e2dde57b9615c8a6b8ea674101f9cfc`, Apache-2.0. Modified: Pi tool boundaries, stop-and-ask on missing design system, manual static detection and bounded verification replace upstream handoffs. See package licenses and notices.

Extraction turns proven repetition into systematic reuse. Consolidate patterns, components and tokens that already repeat with the same intent; do not generalize one-offs or speculate about reuse that has not happened yet. Preserve the incumbent visual world and behavior; premature abstraction is worse than duplication.

## Establish scope and evidence

Follow [target setup](setup.md). Run `node {{PKG_DIR}}/scripts/context.mjs`, adding `--target <path>` when the user names one. Locate the design system, component library or shared UI directory first and study its structure: organization, naming, token shape and import conventions. If no design system exists, stop and ask the user for the preferred location and structure before creating anything.

Use [principles](../references/taste/principles.md) and [components](../references/taste/components.md) as the rule owners, with [taste layout](../references/taste/layout.md), [typography](../references/taste/typography.md), [color](../references/taste/color.md) and [motion](../references/taste/motion.md) inspected against the actual project system. Match existing conventions; never introduce a rival set of defaults inside this procedure.

## Extract systematically

Identify candidates with evidence: repeated components and composition patterns, hard-coded values that should be tokens, inconsistent variations of one concept, and repeated type and animation combinations. Extract only what repeats three or more times with the same intent; leave similar-looking elements separate when their intent differs.

Plan before building: which elements become shared, which values become tokens, which variants each element needs, which names match existing patterns, and how existing uses migrate to the shared versions. Grow the system incrementally; extract what is clearly reusable now.

Build improved shared versions with a clear props surface, sensible defaults, correct variants, accessibility built in, typed interfaces and usage documentation. Name tokens by meaning with a clear primitive-to-semantic hierarchy. Migrate every known instance to the shared version, confirm visual and functional parity, then delete the superseded implementations. Record the new components, tokens and usage guidance in the design system documentation.

NEVER: extract one-off context-specific code without generalization; create components so generic they are useless; ignore existing design system conventions; skip types or prop documentation; tokenize every literal value regardless of meaning; merge elements whose intent differs.

## Verify and finish

Build the scoped change, compare before and after behavior across the migrated instances together, fix observed defects in one batch, then perform at most one confirmation round. Follow setup's explicit local detector path once where supported: run `node {{PKG_DIR}}/scripts/detect.mjs --json <local-file>` against local files only, never URLs, web-only; a clean scan is not proof of parity. If browser or device verification is unavailable, mark those cases unverified rather than pretending a source review exercised them.

Review the source diff for accidental churn, dead imports, duplicated styles and temporary artifacts. Report what changed, concrete verification results, intentional exceptions and remaining limitations. Do not launch another capability or agent as an automatic finish handoff.
