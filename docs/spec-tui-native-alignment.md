# Specification: Native TUI Alignment for Tool Lifecycle and User Input

## Problem Statement

Users of `pi-packages` and its shared runtime `@fradser/pi-kit` observe that tool execution results in the TUI diverge visually from Pi's native design language. In Pi's native theme, tools use `toolSuccessBg` (green) for success and `toolErrorBg` (red) for failure. In contrast, `@fradser/pi-kit` previously styled tool lifecycle rows with `customMessageBg` and `customMessageLabel` (purple in both dark and light themes), and dropped the lifecycle band entirely upon error into a bare text line. Furthermore, teammate names were hashed to a palette that included `success` (green) and `error` (red), confounding teammate identities with execution outcomes, and user-typed query inputs in interactive pickers were unstyled rather than using the native blue (`border`) input color.

## Solution

Align `@fradser/pi-kit` and consumer extensions with Pi's native TUI semantics:
1. Render tool lifecycle rows on `toolSuccessBg` (green) for successful execution with `success` (green) prefixes.
2. Render a symmetrical lifecycle band on `toolErrorBg` (red) with `error` (red) prefixes and expandable error details when execution fails (`context.isError === true`).
3. Style user input text in interactive pickers and dialogs with `theme.fg("border", query)` (native blue).
4. Disambiguate `agentColor` by replacing `success` and `error` with non-status semantic palette tokens (`accent`, `borderAccent`, `mdHeading`, `mdLink`).

## User Stories

1. As a developer using Pi with extensions, I want successful tool executions to display with native green background and accents, so that I can immediately confirm success at a glance.
2. As a developer using Pi with extensions, I want failed tool executions to display with native red background and accents, so that I can immediately identify and diagnose failures without losing tool context.
3. As a developer debugging tool errors, I want failed tool lifecycle rows to be expandable with details, so that error backtraces and messages are easily inspected rather than truncated to a single line.
4. As a user typing in the interactive model search picker, I want my typed query to appear in blue, so that user input is visually distinct from system labels and hints.
5. As a user collaborating with multiple agents, I want agent names to never be colored green or red, so that agent identities are never confused with tool pass/fail status.
6. As an extension author using `@fradser/pi-kit`, I want `createToolLifecycleResultRenderer` and `createStaticToolLifecycleResultRenderer` to automatically handle success (green) and error (red) styling, so that my extension cannot drift from Pi native standards.

## Scenarios

```gherkin
Feature: Native TUI Alignment for Tool Lifecycle and User Input
  As a developer using pi-packages
  I want tool lifecycle rows and user inputs aligned with Pi native tokens
  So that successful tool results are green, failed tool results are red, and user input is blue

  Scenario: Successful tool lifecycle rows render with green background and accents
    Given a tool lifecycle spec for a successful execution
    When renderToolLifecycle is called
    Then the row is rendered on toolSuccessBg background
    And the tool tag and label prefix are styled with theme.fg("success")

  Scenario: Failed tool lifecycle rows render with red background and accents
    Given a tool lifecycle spec for a failed execution with isError=true
    When the lifecycle result renderer produces the component
    Then the row is rendered on toolErrorBg background
    And the tool tag and label prefix are styled with theme.fg("error")
    And expandable error details are preserved in the lifecycle band

  Scenario: Agent color palette excludes success and error tokens
    Given any agent name
    When agentColor computes the color token
    Then the returned token is never "success" and never "error"
    And the palette consists of non-status tokens accent, borderAccent, mdHeading, and mdLink

  Scenario: Interactive search picker styles user query in blue
    Given the model search picker is active
    When the user types a query string
    Then the query is rendered with theme.fg("border", query)
```

## Implementation Decisions

1. **`packages/kit/src/index.ts` - Tool Lifecycle Band Background**:
   - `renderToolLifecycle` accepts an optional `isError?: boolean` parameter in `ToolLifecycleRenderOptions`.
   - `paintBand` computes the background token: when `options.isError` is true, it uses `toolErrorBg`; otherwise, it uses `toolSuccessBg`.
   - The title prefix tag `[tool] label ·` uses `theme.fg(options.isError ? "error" : "success", theme.bold(...))`.
2. **`packages/kit/src/index.ts` - Tool Result Lifecycle Renderers**:
   - `createToolLifecycleResultRenderer` and `createStaticToolLifecycleResultRenderer` inspect `context.isError`. When `context.isError` is true, instead of delegating to an external unpadded `renderError` fallback, they render a lifecycle row with `isError: true`, displaying the error message and expandable error details on `toolErrorBg`.
3. **`packages/kit/src/index.ts` - Agent Color Palette**:
   - Change `AGENT_COLORS` from `["success", "warning", "error", "mdLink"]` to `["accent", "borderAccent", "mdHeading", "mdLink"]`.
4. **`packages/kit/src/index.ts` - Interactive Search Picker**:
   - In `searchModelFromPicker`, the input line query text is styled with `theme.fg("border", query)`.
5. **Consumer Packages Alignment**:
   - Verify and update consumer packages (`agent-teams`, `monitor`, `context`, `utils`, `matt-pocock`, `impeccable`) so their result renderers utilize the updated `pi-kit` contracts.

## Testing Decisions

- **Seam**: Public interface of `@fradser/pi-kit` (`renderToolLifecycle`, `createToolLifecycleResultRenderer`, `createStaticToolLifecycleResultRenderer`, `agentColor`, `searchModelFromPicker`) and consumer test suites.
- **BDD/TDD**: Update `packages/kit/features/pi-kit.feature` and `packages/kit/tests/test_pi_kit.py` with failing tests first, verify red, then implement, verify green, and check all workspace tests.
- **Good Test Criteria**: Tests must inspect the actual emitted ANSI/theme color calls (e.g. verifying `toolSuccessBg` and `success` are used for success, `toolErrorBg` and `error` are used for failures, `border` is used for picker queries, and `agentColor` never returns `success` or `error`).

## Out of Scope

- Overhauling Pi's internal chat bubble rendering (`userMessageBg`, `AssistantMessageComponent`) which are owned by `@earendil-works/pi-coding-agent`.
- Changing the schema or CLI argument contracts of any tool.

## Further Notes

- Maintains backwards compatibility for extension wrappers by keeping structural interfaces.
