/**
 * Terminal geometry for the `agent` tool's lifecycle row.
 *
 * One binding, resolved once, shared by every `agent` result this package
 * paints: a started band like any other background tool rather than the
 * receipt lines a person would otherwise have to read. `@fradser/pi-monitor`
 * and `@fradser/pi-agent-teams` bind the same three functions for the same
 * reason, and a fourth row shape in this harness would be a fourth thing to
 * keep in step.
 *
 * The expand hint is the only part that needs a live theme, so it is a thunk:
 * `bindLifecycleRenderers` resolves it per render inside a guard, which is what
 * lets this module load in a headless process. The width helpers themselves are
 * pure string functions and are safe to import anywhere — the earlier belief
 * that importing pi-tui breaks an unrendered session was `keyHint`, not the
 * import, and the guard is what fixed it.
 */

import { keyHint, ToolExecutionComponent } from "@earendil-works/pi-coding-agent";
import { truncateToWidth, visibleWidth, wrapTextWithAnsi } from "@earendil-works/pi-tui";
import { bindLifecycleRenderers, type createStaticToolLifecycleResultRenderer, type LifecycleRendererBindings, type ToolLifecycleSpec, type ToolLifecycleTheme } from "@fradser/pi-kit";

/** The spec builder a caller passes in; the binding supplies the geometry. */
export type AgentRowSpec = Parameters<typeof createStaticToolLifecycleResultRenderer>[0]["createSpec"];

const agentRows = bindLifecycleRenderers({
  fit: truncateToWidth,
  visibleWidth,
  wrapDetail: (line, width) => wrapTextWithAnsi(line, Math.max(1, width)),
  expandHint: () => keyHint("app.tools.expand", "to expand"),
  hostComponent: ToolExecutionComponent,
});

/** Build the `renderResult` for one row spec. Injected into `registerAgentTool`
 *  so the library stays TUI-free and only the loaded entry paints. */
export function createAgentResultRenderer(spec: { createSpec: AgentRowSpec }): unknown {
  return agentRows.result(spec.createSpec);
}

/** Build the `registerMessageRenderer` callback for a delivered notice row.
 *  Same shared band as every other row, with the host wrapper that gives the
 *  message its click target. The host `ui` and `cwd` are read per render
 *  because only a live session has them. */
export function createSessionMessageRenderer(
  createSpec: (details: unknown) => ToolLifecycleSpec,
  bindings: () => Pick<LifecycleRendererBindings, "ui" | "cwd"> = () => ({}),
) {
  return (
    message: { details?: unknown },
    state: { expanded?: boolean },
    theme: ToolLifecycleTheme,
  ) => agentRows.message(
    (value: { details?: unknown }) => createSpec(value.details),
    bindings(),
  )(message as never, state, theme);
}
