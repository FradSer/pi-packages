# Design judgment

## Scope and authority

This first slice covers component craft, motion and their accessibility constraints, not a complete interface audit. Preserve the product's component library, tokens, density, typography and voice. A stylistic default fills a missing decision; it does not authorize a redesign or dependency migration. Accessibility, functional correctness and explicit user intent constrain those choices.

Use [components](components.md) for controls and surfaces, [motion](motion.md) for animation decisions, and [accessibility](accessibility.md) for semantics, input and preference handling. Apply their scoped exceptions before treating an example as a rule.

## Restraint and feedback

Name the task the design helps. Remove a redundant effect before tuning it; use the platform before rebuilding a control; reuse an existing token before adding one. Prefer immediate, persistent evidence of the outcome over decoration. Delight belongs to rare meaningful moments, not a repeated tax on completing work.

Good defaults reduce configuration, but a control still needs an intentional static option. Loading these references does not authorize edits, dependency installation, variant creation or promotion. A review remains read-only unless implementation is requested.

## Evidence and verification

Distinguish measured runtime behavior, values read from source, calculations derived from measurements, and inference about intent. Never invent usage frequency, rendered contrast, device performance or an animation's feel. A screenshot reveals only its captured state, not keyboard support or motion.

Inspect the real component in its surrounding page with realistic content. Verify hover, keyboard focus, press, disabled, loading, error and empty states when they exist. Test supported widths, zoom and user preferences; name every check not run as **Not verified**. Slow motion and frame-by-frame inspection reveal coordination defects; normal-speed use determines whether the interaction obstructs the task. Gestures need a real device.

Report one root cause once, citing all confirmed locations. Separate accessibility or task failure from stylistic preference. No finding is a valid result, but it is not evidence of coverage you did not inspect. Broader layout, color, writing, exploration and review protocols remain outside this slice.
