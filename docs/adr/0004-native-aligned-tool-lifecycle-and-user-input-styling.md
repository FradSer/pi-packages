# Native-Aligned Tool Lifecycle and User Input Styling

All tool lifecycle rows in `@fradser/pi-kit` and consumer extensions must align with Pi's native TUI theme semantics: successful results render on `toolSuccessBg` with `success` green accents; failed results render on a symmetrical `toolErrorBg` band with `error` red accents; user input in interactive components is styled with native blue (`border`).

## Context

`@fradser/pi-kit` previously rendered tool lifecycle bands using `customMessageBg` and `customMessageLabel`. In Pi's native dark and light themes, `customMessageBg` and `customMessageLabel` are reserved for extension messages and are purple (`#2d2838` / `#9575cd`), while native tools use `toolSuccessBg` (green background) and `toolErrorBg` (red background). Furthermore, failed tool results (`context.isError`) bypassed the lifecycle band entirely, collapsing into a bare unpadded text line. Finally, teammate names were hashed to a palette that included `success` (green) and `error` (red), confounding teammate identities with execution outcomes, while user typing in pickers lacked visual alignment with the blue user/input color language.

## Decision

1. **Tool Lifecycle Success**: `paintBand` renders on `theme.bg("toolSuccessBg", ...)` by default or when status is success. Prefix tag and labels use `theme.fg("success", ...)`.
2. **Tool Lifecycle Failure**: When `context.isError` is true or status is failure, `renderToolLifecycle` renders a symmetrical lifecycle band on `theme.bg("toolErrorBg", ...)` with `theme.fg("error", ...)` tag and labels, and preserves expandable error details instead of falling back to a bare text line.
3. **User Input Styling**: Interactive input and picker query text (e.g., `searchModelFromPicker`) renders with `theme.fg("border", query)` (blue).
4. **Agent Color Disambiguation**: `agentColor` replaces `["success", "warning", "error", "mdLink"]` with non-status semantic tokens `["accent", "borderAccent", "mdHeading", "mdLink"]` to prevent red/green confusion with tool pass/fail states.

## Consequences

- Tool outcomes visually match Pi's native tool execution feedback: green for success, red for error.
- Error diagnostics retain the full-width padded band and expandability matching successful tool rows.
- Teammate names no longer appear in error-red or success-green.
