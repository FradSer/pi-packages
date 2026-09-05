# Motion

## Frequency and input

Decide whether to animate before selecting a tool. Keyboard-initiated actions and actions used `100+ times/day` get immediate state changes, not decorative animation. This is a local interaction policy, not a claim that all keyboard users perform every action hundreds of times. Never infer a measured usage count from an input method.

At tens of uses per day, prefer no animation; a pointer hover may use opacity or background-color at `150ms` or less. Occasional dialogs, drawers and notifications can use standard motion. Rare first-time onboarding, completion and celebration have the expressive budget. Never stagger routine tab changes, keystrokes or list-row hovers. Native platform motion and direct finger tracking require their platform-specific evaluation rather than a blanket web override.

Name the purpose: feedback, spatial consistency, state indication, preventing a jarring change, explanation, or rare delight. Data the user is reading or acting on must not move merely for style. If no purpose survives these gates, keep the state change instant. [Accessibility](accessibility.md#reduced-motion) always governs the preference variant; motion is never the only feedback channel.

## Interruptibility

Never lock out input while a transition finishes. Discrete hover, toggle and open/close state changes should use CSS transitions that retarget from the current interpolated value. A rapidly triggered toast or toggle should not snap back to a scripted start on each update.

Gesture-driven motion is a different scope: track the pointer directly during the drag, then use a spring that starts from the current **presentation value** and carries release velocity. A user must be able to grab, reverse and redirect a moving element. A duration-based CSS transition can retarget a state, but does not by itself provide velocity-continuous grabbing. Reserve pre-scripted keyframes for intentional one-shot or looping sequences, not as the default implementation of a reversible gesture. Keyframes are not inherently impossible to interrupt: WAAPI or explicit control can cancel/reverse them; smooth retargeting still needs deliberate implementation.

Use separate X and Y values when a two-dimensional gesture has independent axis velocities. Verify rapid toggling, Escape during opening, reversal mid-flight, repeated toasts and a second grab during settling. Check both position and velocity continuity rather than merely whether a callback fired.

## Tools and timing

Choose the least expensive existing tool that meets the interaction: CSS transitions for discrete states; `@starting-style` for supported mount-entry transitions; keyframes for staged one-shot sequences; WAAPI for programmatic playback without a dependency; an installed spring/layout/gesture library when those capabilities are needed. Check supported browsers and library versions rather than adding compatibility machinery by habit.

Reuse established easing and duration tokens. Without a product token, deliberate entering/exiting UI can use `cubic-bezier(0.23, 1, 0.32, 1)`; movement or morphing already on screen can use `cubic-bezier(0.77, 0, 0.175, 1)`; a spatial drawer can use `cubic-bezier(0.32, 0.72, 0, 1)`. Hover/color may use `ease`; constant progress uses `linear`. Avoid a slow-start `ease-in` when the user needs immediate response. Do not substitute an unrelated familiar curve or convert every existing curve into this palette.

The press default belongs only to [components](components.md#press-feedback). Small tooltip/popover timing is `125–200ms`, dropdown/select `150–250ms`, centered modal usually `250ms`. Keep ordinary UI at or below `300ms` unless a concrete spatial or established component treatment warrants more. An explicitly spatial drawer recipe may take `500ms` with the drawer curve; a cohesive existing web toast treatment may use `400ms ease`. These are exceptions, not a new universal duration. Marketing explanation can take longer; frequent interactions cannot borrow that budget.

Default ordinary UI springs to no overshoot. A useful non-gesture settle is `{ type: "spring", duration: 0.4, bounce: 0 }`. Momentum-driven or deliberately playful release may use `{ type: "spring", duration: 0.5, bounce: 0.2 }`; do not inject bounce into an ordinary menu. Library duration is a perceptual spring control, not a promise of exact physical settle time. The icon spring is separately scoped in [components](components.md#contextual-icon-changes).

## Entry and exit

For panels, start near the settled size (typically `0.95`) with opacity `0`, not `scale(0)`. Anchored surfaces grow from the trigger; unanchored modals remain centered. A fade without a transform is valid, particularly under reduced motion: do not report every pure fade as physically incorrect.

Preserve the spatial path: a drawer entering from an edge leaves toward that edge. Other content can exit quietly with opacity and a small fixed `translateY(-12px)` in `150ms` rather than flying an entire height. Remove immediately when the motion adds no context. Exit can be shorter than entrance; symmetry of path does not require identical duration or a universal inverse easing curve.

For a rare staged page entrance, group semantic chunks and use about `100ms` between groups; words may use `80ms`. For an occasional list/grid entrance, `50ms` per item is the default within `30–80ms`. These are distinct sequencing scopes, never delays that block interaction. A small `12px` offset with `4px` blur can accompany a page entrance; costly filters still require runtime inspection.

Use `AnimatePresence initial={false}` for elements already in their default state on first render, such as icon swaps, toggles and tabs. Do not apply it to a hero or loading entrance that relies on initial state. Verify a full refresh as well as later state changes.

## Gestures

Track a drag 1:1, preserving where the pointer grabbed the object. Capture the initiating pointer so leaving the bounds does not terminate tracking; ignore extra touch points, handle cancellation, and avoid page-wide gesture suppression. A small movement threshold, around `10px`, helps distinguish a drag axis from scrolling; do not pay double-tap delays unless double-tap is a real feature.

Use recent position/time history for release velocity and retain its sign. A simple flick dismissal can combine a distance threshold with speed above approximately `0.11px/ms`; the right threshold belongs to the actual gesture, not every component. For multi-detent snapping, project where the gesture is heading rather than choosing the closest point to the release position:

```js
function project(velocityPxPerSecond, decelerationRate = 0.998) {
  return (velocityPxPerSecond / 1000) * decelerationRate / (1 - decelerationRate);
}
```

Choose the nearest valid snap point to current position plus projection, then pass release velocity to the spring. `0.99` is a snappier projection option only when intentionally selected. Check the spring API's units: an API expecting relative velocity needs velocity divided by remaining distance, with the zero-distance case handled; Motion uses absolute velocity units. Never interchange those units silently.

At boundaries use progressive resistance rather than a hard wall. A concrete rubber-band curve is `(overshoot * dimension * 0.55) / (dimension + 0.55 * Math.abs(overshoot))`. Prevent inappropriate overshoot past a hard dismissal edge. Test flicks in both directions, slow releases, canceled gestures and re-grabbing on actual touch hardware.

Haptic or audio feedback, where the platform supports it and the product requests it, belongs at a meaningful causal event such as a snap or commit, synchronized with the visual. It is neither per-frame decoration nor the only confirmation. Native API recipes remain outside this web slice.

## Special-purpose transitions

A hold-to-confirm visual uses linear progress during the deliberate hold (`2s`) and a quick reset (`200ms` ease-out). This is not ordinary button latency. Retain an accessible keyboard alternative and explicit cancellation; a painted fill is not the action's implementation.

An accordion may animate measured height and opacity for `200ms` when a transform cannot represent the layout change. Keep the layout cost bounded, use a primitive's measured size where available, and test dynamic content; do not extrapolate a global ban on height into a broken accordion.

A clipped duplicate can synchronize a tab indicator's text and background colors (`250ms` on-screen easing) in an occasional pointer context, but the duplicate must be noninteractive and hidden from assistive technology. Keyboard and frequent tab changes remain instant. Scroll reveals belong to occasional marketing, run once, and disappear under reduced motion; never hide daily-use functional data behind them.

If a crossfade still visibly doubles after timing is tuned, a small `2px` blur can mask the seam; avoid large blur and keep it below `20px`. This general crossfade repair is distinct from the exact contextual icon recipe. Verify the result rather than assuming blur repairs every swap.

## Performance

Name the exact changing properties; never `transition: all`. Prefer transform and opacity to avoid unnecessary layout work. Color, filter, clip-path, shadows and height have different rendering costs; use them only for a justified scoped effect and measure on the target browsers. Neither CSS nor WAAPI guarantees every property is compositor-accelerated. Motion shorthand performance depends on implementation/version and workload; inspect the installed version and profile before replacing working code with a full transform string.

During continuous drag, write the dragged element's transform directly rather than updating an inherited parent CSS variable that can invalidate descendant styles. Avoid React renders or layout reads on every frame where the library supplies continuous values. Add `will-change: transform` or another justified compositing hint only after observing first-frame stutter, and remove temporary hints when no longer useful. Do not pre-promote every element or use `will-change: all`.

For a theme switch, avoid a page-wide smear from simultaneous color/shadow transitions. Prefer the existing theme library's transition-suppression option. A custom switch can temporarily suppress transitions, apply the theme, flush styles, then restore after paint; clean up the temporary stylesheet. Keep this one switch treatment scoped, not a persistent global animation kill switch. An explicit product treatment addressing brightness sensitivity needs separate verification rather than automatic replacement.

Check motion under real loading and scripting work, not only an idle demo. Play at `2–5×` duration or inspect at `10%` speed, step frames, then use normal speed again. Record unmeasured performance as a risk, not a confirmed dropped-frame finding.
