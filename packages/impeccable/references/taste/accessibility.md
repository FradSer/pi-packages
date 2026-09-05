# Accessibility constraints

## Semantics and names

Prefer native elements: buttons perform actions; links with `href` navigate and retain Cmd/Ctrl/middle-click behavior. A role does not implement interaction. Custom controls need the complete keyboard pattern, states and accessible name; avoid rebuilding what the platform or an installed primitive provides.

Prefer visible text or `aria-labelledby` for naming; icon-only buttons require a descriptive name. The visible label must appear in the accessible name for voice control. Decorative SVG and duplicate visual layers are hidden from assistive technology, never by hiding a focusable ancestor. Referenced label/description IDs must exist. Avoid redundant roles and app-menu semantics on ordinary site navigation.

Use a coherent heading outline and one visible primary main landmark; label repeated navigation landmarks. A one-h1/no-skipped-level convention is not by itself proof of a WCAG failure. Add a first-focusable skip link when repeated chrome precedes content, and offset anchored headings beneath sticky chrome.

## Focus and keyboard

Every pointer path needs a keyboard path. Prefer the browser's focus indicator and style `:focus-visible`, not a blanket removal. A custom indicator uses a verified token, at least a `2px` solid perimeter or equivalent visible area, and a useful `2px` offset. Verify the whole perimeter against every adjacent state/background; currentColor is not automatically adequate. Preserve system colors in forced-colors mode.

Use natural DOM order; never positive tabindex. `0` joins the order and `-1` enables programmatic focus. Composite widgets use roving tabindex: one active stop, arrows inside, Tab between widgets, with Home/End where their pattern requires. Tabs activate automatically only when panels are instant; expensive panels need explicit Enter/Space activation. Enter/Space activate buttons, Escape dismisses the most recently opened overlay. Honor the actual APG model instead of attaching arbitrary key handlers.

Prefer native dialog showModal or an established accessible primitive. A modal isolates the background, moves focus inside, traps it, and restores focus to the trigger or a logical successor if it disappeared. Destructive confirmations initially focus the least destructive choice. A custom modal needs its dialog role, modal state and name; `overscroll-behavior: contain` helps prevent scroll chaining but is not a complete substitute for focus and background handling.

On client-side navigation, update document title and move focus to the new heading or main context; preserve sensible back/forward scroll restoration. Do not steal focus for a toast. Keyboard feedback follows [the immediate-state policy](motion.md#frequency-and-input), never an invisible wait for motion to finish.

## Targets and touch

WCAG 2.5.8 AA uses a `24×24` CSS-pixel target or its spacing, equivalent-control, inline, user-agent or essential exception. Do not flag every smaller glyph as a failure: measure its hit area and exceptions. Under the spacing exception, a centered `24px` circle must not intersect another target or another undersized target's circle. A simple pair of `20px` targets therefore needs `4px` separation.

Aim for `44×44px` on touch and `40×40px` desktop where density allows. Native Apple `44pt` and Material `48dp` are different units/platform targets, not replacements for the web AA baseline. Grow the real control box when possible; otherwise expand a button or label's pseudo-element, not a replaced input's unreliable pseudo-element. Expanded targets never overlap.

Label and checkbox form a continuous target. Decorative overlays use pointer-events none so they do not swallow clicks; an intentional dismissing scrim remains interactive. Gate hover-only styling behind hover capability, and hover motion behind `(hover: hover) and (pointer: fine)`. Keep critical affordances available without hover. Scope touch-action choices to the actual gesture; page-wide none disables useful scrolling and zoom.

## Forms and disabled states

Every input has a bound label, not a placeholder substitute. Use meaningful name/autocomplete plus type/inputmode for the actual data: numeric-looking identifiers remain text with numeric inputmode; true quantities can use number. Preserve paste, password managers, autofill and typed values through rerenders. Explain required fields and expected formats before errors occur.

Keep submit enabled so users can discover validation. On submit, show field errors inline, mark aria-invalid, connect aria-describedby and focus the first invalid field. Afterwards, clear errors as corrected and provide helpful inline validation without punishing incomplete typing. Do not filter names or other free text to match an example's arbitrary alphabet. Do not blindly trim secrets or data where whitespace is meaningful.

During a running request, prevent duplicate submission and retain the original label beside a spinner. Native disabled is appropriate when genuinely unavailable. Aria-disabled is for deliberately discoverable/focusable unavailable controls; it does not block behavior, so suppress pointer, keyboard and form activation in code and style it explicitly. Explain why nearby; do not rely on an inaccessible tooltip attached to a native disabled control. Do not set both states redundantly.

## Announcements and persistent state

If focus already moves to the result, no extra announcement is usually needed. Field-specific help/errors use aria-describedby. Non-urgent untied updates use a stable, initially empty role=status region; update its text for repeated announcements. Urgent untied failures alone use role=alert, tested in the supported screen-reader/browser combinations. Avoid duplicate or unnecessarily assertive announcements.

Keep status messages short and self-contained. Updating regions can use aria-busy and announce their outcome. Every state change remains understandable through text, icon or another persistent cue; neither color, animation, sound nor haptics alone is sufficient. Alt text follows purpose: empty for decoration, meaning for information, destination/action for functional images; complex graphics need nearby accessible detail. Prerecorded video needs captions and audio needs an appropriate transcript.

## Reduced motion

Start from a working static presentation. Opt spatial motion in with `prefers-reduced-motion: no-preference`; under reduced-motion, remove slides, scale, zoom, parallax, elastic springs and overshoot. A short opacity crossfade (for example `200ms`) or instant color/icon/label change can preserve comprehension. Reduced motion is not removal of feedback, nor a requirement to animate a fade everywhere. [Press feedback](components.md#press-feedback) becomes nonspatial, not an exception permitting scale.

Stop looping decoration and autoplay; carousels start paused and smooth scrolling becomes instant. Essential progress remains available without requiring spinning or large movement. Existing code that depends on animationend/transitionend must also finish correctly on the static path: do not suppress events and strand functionality. Prefer explicit state completion over a global near-zero-duration override; test any legacy workaround instead of treating it as a complete accessibility solution.

Reduced transparency and increased contrast are independent preferences. Make translucent layers sufficiently solid, remove backdrop blur where requested, and expose a clear contrasting boundary. Forced-colors must preserve usable controls and indicators. Test each signal separately and in combination.

## Timed content

Moving/blinking/updating content that starts automatically and lasts more than `5 seconds` needs an appropriate visible pause/stop mechanism under the applicable WCAG conditions. Never autoplay sound; media controls remain visible. User control is useful even below a formal threshold.

Actionable, error or needed informational toasts stay until explicitly dismissed; critical information also has a durable home. Only low-stakes confirmations may auto-dismiss. The local timeout floor is `5 seconds`, with hover/focus pausing it; pause when the page is hidden where applicable. A library's shorter default is descriptive API behavior, not permission to bypass this policy. Announce without moving the user's focus.

## Zoom and verification

Keep content and functionality usable at `200%` text enlargement and reflow at `320px` CSS width (equivalent to `400%` zoom of a `1280px` viewport). Truly two-dimensional tables/maps/code may scroll within their own containers. Avoid fixed text-container heights and viewport zoom caps. Preserve the project's units, but let content grow; a token does not excuse clipping.

Walk the flow keyboard-only, then inspect accessible names, roles and state with assistive technology. Check focus at every stop, cancellation and restoration, target collisions, errors, zoom, reduced motion and forced colors. Automated checks supplement rather than replace those walks. Measure actual foreground/background contrast against the project's applicable WCAG target; source tokens alone do not establish contrast over transparency or images. Report checks not performed as Not verified, not as passes.
