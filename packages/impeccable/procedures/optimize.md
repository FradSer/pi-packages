# Fix the actual bottleneck for this interface

Adapted from Impeccable `skill/reference/optimize.md` at `cd12f8660e2dde57b9615c8a6b8ea674101f9cfc`, Apache-2.0. Modified: Pi tool boundaries, manual static detection and bounded verification replace upstream handoffs. See package licenses and notices.

Performance is a feature, but only measured performance counts. Identify the actual bottleneck for this interface, fix it, then measure again. Preserve the incumbent visual world, factual copy, behavior and accessibility; a faster interface that breaks function or excludes users is not an improvement.

## Establish scope and evidence

Follow [target setup](setup.md). Run `node {{PKG_DIR}}/scripts/context.mjs`, adding `--target <path>` when the user names one. Measure the current state first: load behavior, bundle weight, render cost and network shape for the requested path. Name what is slow, what causes it, how bad it is and who it affects before changing anything. Optimize the biggest bottleneck first; do not spend the pass on micro-optimizations while the dominant cost stands.

Use [principles](../references/taste/principles.md), [components](../references/taste/components.md) and [motion](../references/taste/motion.md) as the rule owners. Inspect loading, rendering and animation behavior against the actual project system; disclose missing specialized guidance rather than inventing a parallel set of numeric defaults here.

## Optimize systematically

Treat loading as the usual suspect: right-sized modern images with lazy loading below the fold, split bundles with deferred non-critical code, trimmed styles with critical CSS first, restrained font loading with fallback display, and prioritized critical requests with caching and compression. Never lazy-load above-fold content.

Treat rendering as the second suspect: batch reads before writes, flatten and shrink the DOM, isolate independent regions, reserve space for late content so layout does not shift, and keep movement on cheap properties within the canonical motion constraints. Use explicit layer hints sparingly and only for known expensive operations.

Treat interaction as the acceptance test: hold the line on contentful paint, interaction latency and layout stability; break up long tasks, defer non-critical work, and confirm slow-connection and low-end-device behavior rather than flagship-only results. Measure on real devices and real network conditions; desktop-class browsing on fast connections is not representative.

NEVER: optimize without measuring first; sacrifice accessibility for speed; break functionality while optimizing; spray layer hints everywhere; lazy-load above-fold content; chase micro-optimizations while ignoring the dominant bottleneck; verify on flagship hardware only.

## Verify and finish

Build the scoped change, compare before and after measurements on the same path and conditions, fix observed regressions in one batch, then perform at most one confirmation round. Follow setup's explicit local detector path once where supported: run `node {{PKG_DIR}}/scripts/detect.mjs --json <local-file>` against local files only, never URLs, web-only; a clean scan is not proof of user-perceived speed. If device, browser or throttled-network verification is unavailable, mark those cases unverified rather than pretending a source review exercised them.

Review the source diff for accidental churn, dead code, duplicated styles and temporary artifacts. Report what changed, concrete verification results, intentional exceptions and remaining limitations. Do not launch another capability or agent as an automatic finish handoff.
