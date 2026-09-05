# Component craft

## Press feedback

For an occasional pointer/touch press that benefits from tactile feedback, the local default is `scale(0.96)` with a `150ms` CSS transition. This is a selected house recipe, not a measured optimum. Preserve an established project token or motion treatment when it serves the same purpose; do not introduce a parallel token system. Do not exaggerate the scale below `0.95`.

Feedback starts on press-down; committing the action retains the native activation behavior, usually release/click. Never commit a destructive action merely because pointer-down occurred. Keyboard activation changes state immediately with a static cue, without press-scale animation. A static component option disables the scale where it distracts. Reduced-motion and high-frequency use also take the nonspatial path. These gates come from [frequency and input](motion.md#frequency-and-input) and [reduced motion](accessibility.md#reduced-motion), not a second component animation policy.

Implement a discrete press with the [retargetable transition rule](motion.md#interruptibility), naming only the property that changes. Keep hover, disabled and focus semantics independent of scale. Exclude both native disabled and intentionally aria-disabled controls from visual press feedback; the latter also needs activation blocked in code. Verify early release, cancellation, repeated activation, keyboard activation and the static option. Preserve a label, icon or state color after the animation ends.

## Nested surfaces

For visibly close, evenly inset rounded surfaces, `outer radius = inner radius + padding`. At more than `24px` padding, treat the layers as independent surfaces rather than forcing concentric math. Preserve deliberate asymmetric insets and independent component tokens.

Optical alignment corrects a visible imbalance, not every mathematically centered element. For a text-and-icon button, start the icon-side padding `2px` smaller than the text side if necessary; use logical padding for reading direction. A play triangle can need a physical `2px` rightward nudge. Prefer correcting an asymmetric SVG's viewBox or path over accumulating wrapper offsets. Check at actual render size.

## Elevation and separators

Use transparent layered shadows where a border exists only for elevation. Keep structural dividers, table boundaries, input outlines and selected/focus indicators. Depth must not erase the accessible boundary of a control.

When no project elevation token exists, a restrained light surface recipe is a ring `0 0 0 1px oklch(0 0 0 / 0.06)`, a lift `0 1px 2px -1px oklch(0 0 0 / 0.06)`, and ambient shadow `0 2px 4px 0 oklch(0 0 0 / 0.04)`. Hover alphas are `0.08`, `0.08`, `0.06`. In dark mode, a single white ring `0 0 0 1px oklch(1 0 0 / 0.08)` (hover `0.13`) often communicates more than invisible black shadows. Match the existing theme mechanism and verify against the actual background.

For images needing an edge separator, use a `1px` outline, `outline-offset: -1px`, pure black `oklch(0 0 0 / 0.1)` in light mode and pure white `oklch(1 0 0 / 0.1)` in dark. This scoped neutral separator is not a prescription to replace the product's color palette with black and white. An outline does not add layout size.

## Icons

Keep one coherent optical strategy per surface. On a `24px` icon grid, starting stroke widths are `1.5px` beside regular `400` text at `14–16px`, `2px` beside `500–600`, and `2.5px` beside bold `700` or emphasized standalone icons. If a library has no stroke variants, preserve its native stroke and adjust size or color, rather than distorting the set. Inline icons usually fit at `1em–1.25em` relative to text.

Use SVG and test its smallest real size, often `16px`. Prefer the library's native `16`, `20`, or `24` grid over arbitrarily shrinking detailed artwork. One `currentColor` asset receives hover, selected and disabled colors from CSS. Where available, outline is the default and fill conveys active state; never make color the only state cue.

Mirror direction-dependent navigation, indentation and send glyphs in RTL, not brand marks, checkmarks, physical objects or conventional media playback. Inspect composite overlays separately. Decorative icons are hidden from assistive technology; icon-only controls need [accessible names](accessibility.md#semantics-and-names).

## Contextual icon changes

Animate a meaningful occasional icon swap, not permanently visible navigation or decorative icons. Apply the input/frequency and reduced-motion gates first. The scoped icon recipe is opacity `0` to `1`, scale `0.25` to `1`, blur `4px` to `0px`; it is not the entrance recipe for a whole panel.

With an existing Motion dependency, use a spring `{ type: "spring", duration: 0.3, bounce: 0 }`. Import from `motion/react` for `motion`, or `framer-motion` for that installed package; follow nearby imports if both exist. Do not add either for an icon swap. Without one, keep both icons in the DOM, one absolutely overlaid and one establishing size, and transition opacity/filter/scale for `300ms` using `cubic-bezier(0.2, 0, 0, 1)`. This curve belongs to this icon recipe, not the general motion token.

The duplicated artwork must not duplicate accessible names, focus stops or hit targets. Keep the control's name and state meaningful throughout. For default-state swaps, suppress an unnecessary first-render entrance; preserve intentional staged entrances. See [entry and exit](motion.md#entry-and-exit).

## Anchored and transient controls

Popover, menu and tooltip transforms originate at the trigger, using the primitive's supplied origin when available. An unanchored centered modal stays centered. Tooltips delay the first hover to prevent accidental activation; adjacent tooltips in the same open group skip both delay and animation. Do not make hover the only way to discover information.

Keep modal focus, keyboard dismissal and background isolation in [accessibility](accessibility.md#focus-and-keyboard). Toasts announce without stealing focus, retain actions/errors until dismissed, and obey [timed content](accessibility.md#timed-content). Prefer an installed accessible primitive over hand-built interaction plumbing.

## Optional translucent materials

Use translucency only when the product calls for floating material hierarchy. Avoid stacking light translucent surfaces; verify contrast against the changing content behind them. Larger surfaces may need more separation, not indiscriminately more blur. A modal scrim signals a blocking task; a parallel panel should not dim the entire workspace as if it blocks it.

Reduced transparency makes materials solid and removes backdrop blur; increased contrast needs stronger boundaries and sufficiently opaque backgrounds. These are independent signals from reduced motion. Do not impose translucent chrome or animated blur on every product. Follow [performance](motion.md#performance) before animating an expensive material.
