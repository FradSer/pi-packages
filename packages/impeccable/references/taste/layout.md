# Layout

## Scope and grouping

Preserve usable project density, platform chrome and spacing tokens. Defaults below fill a missing system, not justify expanding a compact professional tool. Space groups first, background shapes second, separator lines last. Between-group gaps should be at least `2×` within-group gaps: `8px` inside implies `16px` or more between. Dense tables and long settings lists can retain quiet structural separators; do not add both a large separating gap and an unnecessary line.

Controls must be distinguishable from static content by shape, border, underline or a consistent control zone. Conversely, a static badge should not imitate its neighboring buttons so closely that it invites dead clicks. Emphasis and interaction must remain legible without depending on color alone; the constraint belongs to [accessibility](accessibility.md#announcements-and-persistent-state).

## Alignment and order

Choose a few shared edges rather than unrelated offsets. Use one project spacing step for nested hierarchy; `16px` is a starting point without an existing scale. Keep identifying content leading, metadata/actions trailing; align table text to the leading edge and comparable numbers to the trailing edge. Numeric glyph widths belong to [typography](typography.md#numbers-and-direction).

Order content by importance, top-to-bottom and leading-to-trailing. Give the primary task room; move secondary detail deeper without hiding its existence. Once secondary actions exceed two or three, consider an established menu rather than flattening every action into the entry view. Visual order must not contradict [keyboard reading order](accessibility.md#focus-and-keyboard).

Use logical margin, padding, inset, borders and text alignment where position follows language. Keep physical coordinates where they describe a notch, physical glyph correction or a gesture edge. Progression and navigation can mirror in RTL; do not reverse digits or indiscriminately flip physical/media icons. The glyph rules belong to [components](components.md#icons).

## Targets and margins

Absent an established density system, start with `12px` between bordered/filled controls and `24px` around borderless controls. Unrelated groups need at least twice their internal gap. These are usability starting points, not conformance minimums: compact layouts may use less while remaining distinct. Measure actual and expanded hit areas against the single [target policy](accessibility.md#targets-and-touch), rather than stacking conflicting minimums.

Inset full-width content buttons within layout margins, starting at `16px` inline on mobile, with a visible shape. Intentional edge-to-edge platform chrome remains valid when it respects safe areas and reads separately from system controls. Backgrounds and media may bleed; text and controls stay within margins and safe areas. Floating/sticky controls account for `env(safe-area-inset-*)` and do not cover the content or action they serve.

## Disclosure and adaptation

Offscreen and collapsed content needs a visible cue. Preserve the product's established scroll indicator, or let the next item peek `16–32px`, or supply a labelled disclosure such as “Show 12 more results”. An exact-fit carousel with no hint falsely looks complete. An ellipsis indicates truncation but does not alone make the missing value available; follow [truncation](typography.md#wrapping-and-truncation).

Break where content ceases to fit, not because a device preset has a familiar number. Preserve expanded structure until it genuinely fails; do not collapse early and waste available space. Prefer container queries when a component's column width, not the viewport, governs its layout. Framework defaults may be appropriate; matching a preset is not evidence nobody evaluated it.

Test smallest and largest supported widths first, then intermediate failure points. Use pseudo-localization and a representative long-string locale: there is no universal expansion percentage, and short labels often grow proportionally most. Let buttons size from labels and padding, allow rows to wrap, and replace fixed text-container sizes with growing boxes. Keep critical actions in normal flow or stable chrome; a resizable pane, expanding keyboard or scrolling modal must not clip the only way to finish.

## Verification

Inspect the actual page, not only an isolated component. Check shared edges, group relationships, disclosure cues, overflow, safe areas and each supported density. Test RTL with real mixed-direction content and translated labels, not a screenshot flip. [Zoom and reflow](accessibility.md#zoom-and-verification) remains the authoritative accessibility gate. Record unvisited widths and modes as Not verified; propose layout changes only for demonstrated task, hierarchy or adaptation problems.
