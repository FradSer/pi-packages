# Refine layout relationships

Adapted from Impeccable `skill/reference/layout.md` at `63b04e2530f5c7b41ea83c133daab24f34912456`, Apache-2.0. Modified for Pi: canonical layout rules own numerical defaults; unsupported scope flags, subagent/native links and live-mode handoffs are removed. See package licenses and notices.

Follow [setup](setup.md) and [layout guidance](../references/taste/layout.md). Diagnose the structural problem before moving elements. Preserve the established identity and everything outside scope.

Assess reading order, grouping, rhythm, topology, density and adaptation using representative content and sizes. Blur detail mentally or visually to check whether primary, secondary and major groups remain distinguishable. Use source or rendered evidence, not unexplained declarations that spacing feels wrong. Keep this assessment independent from mechanical findings.

State the primary task path, what belongs together, what leads, the intended density and how structure changes with container, viewport, input and content extremes. Choose the simplest model expressing these relationships. The canonical topic owns grouping ratios, spacing defaults and exceptions; preserve existing product tokens rather than imposing a second grid.

Apply structural responsive behavior, meaningful proximity and consistent roles. Verify DOM, focus and visual order agree. Inspect overlays, sticky elements, clipping, safe areas, long strings, empty states, zoom and localization; do not treat arbitrary breakpoint conventions as evidence of poor design.

Inspect supported cases together, fix observations in one batch and confirm at most once. Use setup's supported static-file scan where helpful, not upstream directory or scope flags. Report evidence and limitations: a clean scan cannot prove hierarchy, and source inspection cannot prove rendered optical alignment. Do not automatically trigger polish, agents or live previews.
