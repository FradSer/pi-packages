# Bring users to first value fast

Adapted from Impeccable `skill/reference/onboard.md` at `cd12f8660e2dde57b9615c8a6b8ea674101f9cfc`, Apache-2.0. Modified: Pi tool boundaries, manual static detection and bounded verification replace upstream handoffs. See package licenses and notices.

Onboarding is not teaching the product. Its job is to get people to the moment that proves the product is worth their time, then get out of the way. Preserve the incumbent visual world, factual copy and behavior; if the concept itself is wrong, report that separately rather than replacing it under the name of onboarding.

## Establish scope and evidence

Follow [target setup](setup.md). Run `node {{PKG_DIR}}/scripts/context.mjs`, adding `--target <path>` when the user names one. Establish what users are trying to accomplish, where they stall or drop off, and which single action constitutes first value. Ask for the missing context up front: the intended aha moment and the users' experience level. Define success as the minimum learning that produces that action, not coverage of every feature.

Use [principles](../references/taste/principles.md), [components](../references/taste/components.md) and [writing](../references/taste/writing.md) as the rule owners. Inspect the requested path against the actual project system and its existing empty states, hints and help patterns; disclose missing specialized guidance rather than inventing a parallel set of defaults here.

## Design the shortest path

Show, do not tell: demonstrate with working product and real functionality, one idea at a time, closest to the point of use. Front-load the 20 percent that delivers 80 percent of the value; teach advanced features through contextual discovery, not upfront ceremony. Keep welcome, setup and first-success guidance to the minimum that reaches value: a clear proposition, honest time estimate, smart defaults, one to three core concepts, and a real accomplishment with a clear next step.

Make onboarding skippable wherever possible and never block access to the product for the sake of a tour. Treat empty states as the primary surface: say what will appear, why it matters, and how to start, with a creation action and a template or example option. Keep tours to seven steps or fewer, freely skippable and replayable; keep tooltips brief, dismissible and shown once. Track seen and dismissed states and respect them.

NEVER: force a long flow before users can reach the product; patronize with obvious explanations; show the same hint twice after dismissal; block all exploration during a tour; build a tutorial mode detached from the real product; front-load everything instead of disclosing progressively; hide or omit a skip path; forget returning users by replaying first-run guidance.

## Verify and finish

Build the scoped change, walk the full path to first value including empty, error and skip cases together, fix observed defects in one batch, then perform at most one confirmation round. Follow setup's explicit local detector path once where supported: run `node {{PKG_DIR}}/scripts/detect.mjs --json <local-file>` against local files only, never URLs, web-only; a clean scan is not proof of onboarding quality. If real-user or device verification is unavailable, mark those cases unverified rather than pretending a source review exercised them.

Review the source diff for accidental churn, dead code, duplicated styles and temporary artifacts. Report what changed, concrete verification results, intentional exceptions and remaining limitations. Do not launch another capability or agent as an automatic finish handoff.
