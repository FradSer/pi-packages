# Add motion with a defined job

Adapted from Impeccable `skill/reference/animate.md` at `63b04e2530f5c7b41ea83c133daab24f34912456`, Apache-2.0. Modified: timing/easing and accessibility rules are owned by the unified taste references; unsupported platform links, blanket motion advice and automatic command handoffs are removed. See package licenses and notices.

## Find the job

Follow [target setup](setup.md). Inspect existing interaction states, motion tokens, dependencies, target devices and performance constraints. Motion should acknowledge an action, explain state or relationships, preserve continuity, direct attention at a meaningful moment, or serve an explicitly requested expressive moment. Static areas do not need animation merely because they exist.

Use [principles](../references/taste/principles.md), [motion](../references/taste/motion.md) and [accessibility](../references/taste/accessibility.md). They own purpose/frequency filters, input distinctions, exact defaults, interruptibility and reduced-motion behavior. Do not treat upstream duration examples as a competing policy. If implementing a component-specific recipe, first load its canonical component guidance through `impeccable_load`; loading a reference itself does not authorize edits.

## State a small implementation plan

Identify the interaction's cause and observable result, any continuity that needs explanation, the focal moment if justified, how often it occurs, and the runtime budget. Routine application and reading tasks must not wait for decorative choreography. Expressive sequences require a product-specific purpose rather than repeated generic scroll reveals.

Prefer existing project primitives and dependencies. Select material by meaning: spatial continuity, controlled reveal, depth, or minimal feedback. Avoid stacking effects. Verify APIs against the installed runtime; do not assume a property or library always runs on the compositor. Do not install a dependency without authorization.

## Implement and verify

Keep content visible and usable when scripts fail. Retarget from the current presentation state and preserve velocity where direct manipulation requires it. Verify rapid reversal, repeated input, keyboard paths and the reduced-motion alternative using the same canonical rules applied during implementation. Expensive blur, shadows, canvas or shaders need measured evidence on the actual target device, not a claim that transforms guarantee speed.

Inspect the scoped behavior in one batched pass, fix observed defects, then perform at most one confirmation round. Use setup's static detector only for supported local files; it cannot establish animation quality or frame performance. Do not apply web recipes to a native request without verified platform guidance. Report missing device/browser evidence and unsupported platform branches explicitly.

Finish with the purpose of each retained animation, tested states and inputs, performance evidence available, and remaining limitations. Recommend a later polish pass only when useful; do not trigger a new turn, install, agent or capability automatically.
