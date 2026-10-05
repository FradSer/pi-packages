# btw TUI Design Review

## Scope and result

Review the current btw interaction and compare shared UI responsibilities with other packages.
This report records the pre-fix review. The user subsequently authorizes all findings for implementation.
Read @../../packages/btw/CONTEXT.md for current fixes and verification.
The accepted minimum is 20 columns and 8 rows. Home and End edit the visible composer.
Configured cancel bindings apply in loading and idle states; literal Escape remains available.

Read @../../packages/btw/CONTEXT.md for implementation and verification state.
Read the installed Pi `docs/tui.md` when implementing the proposals below.

The modal overlay remains appropriate for a temporary, multi-turn side conversation.
The existing package boundaries are mostly correct. Do not introduce a generic chat-overlay framework.

## Evidence and comparison

| Package | Interaction | Shared capability | Package responsibility |
| --- | --- | --- | --- |
| btw | Bottom overlay with conversation and input | Panel frame, theme callbacks, scroll window | Turns, usage, cancellation, prompt history |
| Open DeskOS | Session console with attached input | Native `Input` and focus delegation | Session selection, attachment, prompt delivery |
| agent-teams | List, detail, and model-picker console | Panel frame, theme, picker helpers | Selection, detail transitions, live refresh |
| monitor | List and output console | Panel frame, theme | Monitor selection and stop actions |
| goal | Read-only dashboard | Panel frame, height and scroll helpers | Goal details and dashboard navigation |
| skill-router | Cancellable loading overlay | Panel frame, theme, native loader | Operation completion and cancellation result |
| recap | Passive Markdown widget | Theme callbacks and native Markdown | Recap content and widget lifecycle |

Source references:

- @../../packages/btw/src/overlay.ts: input, scrolling, rendering, and cancellation.
- @../../packages/btw/src/index.ts: production command and overlay options.
- @../../packages/open-deskos/src/console-extension.ts: delegated `focused` accessors.
- @../../packages/agent-teams/src/ui.ts: list/detail/picker modes and separate viewport budgets.
- @../../packages/monitor/src/index.ts: shared frame and package-owned selection.
- @../../packages/goal/src/dashboard.ts: shared scroll helper and read-only navigation.
- @../../packages/skill-router/src/menu.ts: operation cancellation with idempotent completion.
- @../../packages/recap/extensions/index.ts: shared Markdown callbacks with a theme-owner cache.
- @../../packages/kit/src/index.ts: shared frame, scroll window, height, and Markdown callbacks.

## Confirmed findings

### 1. The scroll helper does not clamp negative offsets

**Evidence:** `computeScrollWindow(["a", "b", "c"], -1, 2)` returns start `-1`, end `1`, and clamped scroll `-1`.
The implementation applies only the upper bound. btw passes `scroll + delta` directly.
Thus an upward step from the first line can produce an empty or incorrect window.
Goal clamps its own navigation before calling the helper, which hides this shared defect there.

**Owner:** pi-kit. Clamp the offset between zero and the maximum offset.

**Compatibility:** Preserve the signature and positive-offset behavior. Negative values have no useful supported viewport meaning.

**Verification:** Add a negative-offset regression at the existing kit test seam.
Test top-boundary upward movement in btw and retain the goal dashboard tests.

### 2. btw does not delegate focus

**Evidence:** Pi's `isFocusable(overlay)` returns false for the btw component.
The component sets `input.focused = true`, but exposes no `focused` property.
Open DeskOS already delegates this property through getters and setters.
Installed Pi uses that property when switching overlay focus.

**Owner:** btw. Implement the native `Focusable` contract and delegate focus to its input.
Do not force focus on every completed turn if the host has moved focus elsewhere.

**Compatibility:** Add the focus property without removing existing callbacks.
Keyboard receipt and child focus are separate concerns; existing keyboard success does not prove correct focus propagation.

**Verification:** Toggle component focus and check cursor-marker visibility.
Test stacked overlays, hide/show transitions, and restoration to the main editor through a real TUI.
Final screen cursor position and IME candidate placement require additional verification.

### 3. Scroll navigation competes with composer editing

**Evidence:** Type `x`, press Home, and type `y`. The composer shows `xy`, not `yx`.
btw intercepts Home/End before forwarding input to native `Input`.
Its current footer explicitly advertises these keys for scrolling, so this is a documented design trade-off.

**Owner:** btw. Choose and document separate transcript and composer navigation.
A candidate keeps Up/Down and PageUp/PageDown for the transcript, while Home/End edit the composer.
Another candidate uses an explicit transcript-focus mode with a clear focus indicator.

**Compatibility:** Changing Home/End breaks the documented key contract. Obtain acceptance before implementation.
Do not silently change the keys or introduce a shared key router for this package-specific decision.

**Verification:** Test cursor movement inside a nonempty question, transcript navigation, and configured submit/cancel bindings.
Verify behavior while loading and after errors.

### 4. A fixed row reserve is not a complete small-terminal design

**Evidence:** At 16 terminal rows, a completed overlay generates 14 lines. Its 80% limit is 12 lines.
The current one-row minimum cannot satisfy the limit after the fixed 13-row reserve.
The existing PTY regression covers 24 and 40 rows, not smaller heights.
The footer also places usage before controls, so narrow widths can hide the available actions.

**Owner:** btw. Define normal, compact, and minimum-size layouts before extracting shared geometry.
Compute space from the actual header, footer, composer, and loading rows.
Reduce decorative spacing before removing the input or essential controls.
At an unusable size, keep a close action and display a size requirement.

**Compatibility:** Preserve the zero bottom margin and normal-size layout.
Keep 40% as the preferred answer cap, not a minimum or a total panel budget.
The exact minimum size and compact layout need acceptance.

**Verification:** Table-driven layouts at 12, 16, 18, 24, and 40 rows, with narrow and normal widths.
Cover loading, answered, error, and long-question states.
Use final screen evidence to verify that Pi does not clip the composer or footer.

### 5. Invalidation stops loading animation

**Evidence:** btw's `invalidate()` calls `loader.stop()` and invalidates only Markdown.
Pi defines invalidation as cache refresh, including theme changes; it does not mean cancellation or disposal.
The native loader provides its own `invalidate()` method without stopping its animation.

**Owner:** btw. Invalidate the loader, Markdown, and input caches without ending active work.
Stop resources only at turn completion, cancellation, or disposal.

**Compatibility:** This preserves the lifecycle contract. It changes spinner behavior only when invalidation occurs during loading.

**Verification:** Invalidate while a deferred turn remains active.
Verify continued render requests and answer completion, then verify no requests after disposal.

### 6. Mouse documentation describes an obsolete host limitation

**Evidence:** Installed Pi 1.0.0 defines `Component.handleMouse` and normalized wheel events.
Its fullscreen renderer dispatches wheel events to overlays before transcript fallback.
btw instead parses raw SGR sequences inside keyboard handling.
The README and @../../packages/btw/.memory/btw_package_design.md contain the obsolete claim: “Mouse wheel: impossible for extension UI”.
Pi also forwards raw wheel input to a focused overlay when normalized dispatch finds no handler.
Thus the former SGR parser is reachable through a compatibility fallback, not necessarily dead code.
Native wheel routing must pass a PTY reproduction before removing that fallback.

**Owner:** btw for event handling and documentation. Pi owns terminal protocol decoding.
Use native `handleMouse` or evaluate native `ScrollView`; retain a keyboard path.
Do not add another mouse parser to pi-kit.

**Compatibility:** Fullscreen mouse handling differs from regular terminal scrollback.
Verify supported host versions before deleting a compatibility path or promising wheel support.
Memory corrections must follow the repository's canonical-memory synchronization rule.

**Verification:** Send a wheel event over the answer body through the PTY.
Verify no transcript scroll, no composer corruption, and keyboard parity.
Test regular mode separately and document its terminal-owned scrolling.

## pi-kit abstraction decisions

### Keep the existing panel frame

`renderPiPanel` already serves btw, agent-teams, monitor, goal, and skill-router.
Keep it a pure width-bounded renderer. It must not own interaction or transcript state.

A measured layout helper is a possible later addition, not an immediate requirement.
First establish the compact btw layout and verify the same measurement need in another consumer.
If shared, accept total rows and measured fixed rows; do not encode btw's 13-row reserve or 40% preference.
Changing the frame's inset or row count requires consumer verification.

### Keep turn lifecycle in btw

Initial cancellation closes the popup. Follow-up cancellation removes one pending turn and preserves completed turns.
Skill-router cancellation instead settles an operation with an error.
Open DeskOS cancellation targets an attached session.
These meanings differ. A generic shared cancellation state machine would obscure ownership.

Keep history filtering, usage totals, loading/error states, and legacy callbacks in btw.
Avoid a generic conversation component until another package requires the same observable behavior.

### Repair shared primitives before adding more

Fix the negative scroll bound in the existing helper.
Keep focus delegation and native `Input` composition local; they require only small accessors.
Use Pi's native mouse, key, width, and cursor APIs rather than wrappers.

Evaluate `ScrollView` against required bottom-follow behavior before changing the scroll implementation.
Do not keep both independent scroll offsets and a `ScrollView` offset.
A migration requires real resize, keyboard, and wheel tests.

### Remove theme transport markers in a separate compatible change

`buildMarkdownThemeCallbacks().hr()` returns `__OVERLAY_SEPARATOR__` rather than a display line.
btw recognizes and replaces it during rendering.
Recap also consumes the same callbacks, so this is not a private btw implementation detail.
An authored answer containing the marker can also be interpreted as a separator.

pi-kit owns theme callbacks. Consumers own available width.
Native `MarkdownTheme.hr(text)` already receives a width-bounded separator from Markdown.
Style that supplied text instead of adding another width-aware interface.
Do not silently change the shared callback result without checking recap and btw Markdown output.
Test authored marker text, horizontal rules, and narrow widths in both consumers.

### Correct kit guidance before extending its interface

`packages/kit/AGENTS.md` describes Pi peers, then tells tests to keep peer dependencies absent.
The README describes the allowed pi-tui import, then claims that no Pi core imports exist.
The current manifest and runtime contain the documented peers and pi-tui import.
Reconcile these statements in their authoritative sections before implementing new shared APIs.
No dependency change is required for focus or mouse support in btw.

## Implementation order

1. Fix negative scroll bounds with a shared regression and consumer checks.
2. Correct btw focus delegation and invalidation without changing key assignments.
3. Verify native wheel routing and revise host-version claims.
4. Obtain acceptance for composer keys and compact layout behavior.
5. Implement the accepted layout locally and add final screen and cursor verification.
6. Extract a measured layout helper only after a second consumer demonstrates the same need.

## Verification and limits

Local read-only probes confirm negative scroll, missing focus delegation, Home interception, and 16-row overflow.
These probes use native components and synthetic terminal dimensions, not final screen rendering.
Source review confirms invalidation and native mouse routing. No manual IME check occurs.

The prior task verifies 27 btw tests, eight root entry tests, package and root TypeScript, packing, and configured installation.
Those checks do not resolve the design findings above.
The existing PTY test bypasses the production command handler and child process by design.
Use it for UI behavior, not as proof of the complete `/btw` execution path.

## Acceptance questions

- Should Home/End edit a question, or keep their current transcript-navigation behavior?
- Should compact mode remove separator rows and shorten the footer before restricting the answer viewport?
- What minimum terminal width and height must btw support?
- Must configured `tui.select.cancel` bindings work in every turn state?

Resolve these questions before material interaction changes. The low-risk focus, invalidation, and scroll fixes do not require new abstractions.
