# Rethink the experience for the new context

Adapted from Impeccable `skill/reference/adapt.md` at `cd12f8660e2dde57b9615c8a6b8ea674101f9cfc`, Apache-2.0. Modified: Pi tool boundaries, web-only responsive scope with native unavailability report, manual static detection and bounded verification replace upstream handoffs. See package licenses and notices.

Adaptation is rethinking the experience for the new context, not scaling pixels. Preserve the incumbent visual world, factual copy and information architecture; what changes is layout, interaction, content priority and navigation behavior. If the concept is wrong for the target, report that separately rather than reshaping it silently.

## Establish scope and evidence

Follow [target setup](setup.md). Run `node {{PKG_DIR}}/scripts/context.mjs`, adding `--target <path>` when the user names one. Establish the source assumptions (screen size, input, connection) and the target constraints (device, input method, orientation, connection, usage context, platform expectations). Ask for the missing context up front: target platforms, devices and usage contexts. Name what will not fit, what will not work and what is inappropriate before changing anything.

Responsive and breakpoint guidance in this procedure is web-only, mobile web included. If the project is native (ios, android or adaptive per setup), native adaptation guidance is reported unavailable; do not substitute web measurements for native behavior.

Use [principles](../references/taste/principles.md), [components](../references/taste/components.md) and [taste layout](../references/taste/layout.md) as the rule owners, with [typography](../references/taste/typography.md) inspected against the actual project system; palette stays as the project defines it. Disclose missing specialized guidance rather than claiming coverage from this procedure alone.

## Adapt systematically

Restructure layout per context: single-column vertical stacking and bottom or drawer navigation for phones; hybrid two-column and master-detail for tablets with orientation considered; multi-column and persistent side navigation for desktop with sane maximum widths; stripped single-column output for print and email. Drive breakpoints from content rather than device myths; three content-driven breakpoints usually suffice, with fluid sizing between them.

Match interaction to input, not screen size: minimum 44px touch targets with generous spacing and no hover-dependent behavior where touch applies; hover, keyboard, context and drag affordances where fine pointers apply; large obvious calls to action and deep links out for email. Detect pointer and hover capability rather than guessing from width, and honor safe-area insets on modern phones. Keep core functionality working in every context; never hide what matters on the smaller surface.

Reprioritize content per context: progressive disclosure and concise copy on small screens; fuller disclosure, tables and richer visualization on large ones; expanded URLs, page structure and metadata for print. Prefer lazy loading and responsive images for the web; confirm landscape, very small and very large viewports explicitly.

NEVER: hide core functionality on the smaller context; assume capable hardware from screen size; fork the information architecture per context; violate target-platform expectations; ignore landscape orientation; apply generic breakpoints blindly; ignore touch on pointer-first surfaces.

## Verify and finish

Build the scoped change, inspect the source and target contexts together across representative viewports, orientations and input cases, fix observed defects in one batch, then perform at most one confirmation round. Follow setup's explicit local detector path once where supported: run `node {{PKG_DIR}}/scripts/detect.mjs --json <local-file>` against local files only, never URLs, web-only; a clean scan is not proof of adaptation quality. Device emulation is not device proof: if real-device, browser or OS verification is unavailable, mark those cases unverified rather than pretending a source review exercised them.

Review the source diff for accidental churn, dead code, duplicated styles and temporary artifacts. Report what changed, concrete verification results, intentional exceptions and remaining limitations. Do not launch another capability or agent as an automatic finish handoff.
