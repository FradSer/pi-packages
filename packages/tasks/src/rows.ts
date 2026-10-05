/**
 * Terminal geometry for the `task` tool's lifecycle row.
 *
 * One binding, resolved once, shared by every `task` result this package paints:
 * the same shared band every other tool in this workspace uses, rather than a
 * fourth row shape to keep in step.
 *
 * The expand hint is the only part that needs a live theme, so it is a thunk:
 * `bindLifecycleRenderers` resolves it per render inside a guard, which is what
 * lets this module load in a headless process.
 */

import { keyHint, ToolExecutionComponent, type ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { truncateToWidth, visibleWidth, wrapTextWithAnsi } from "@earendil-works/pi-tui";
import {
  bindLifecycleRenderers,
  type createStaticToolLifecycleResultRenderer,
  type ToolLifecycleSpec,
} from "@fradser/pi-kit";

/** The spec builder the tool hands in; the binding supplies the geometry. */
export type TaskRowSpec = (
  result: Parameters<Parameters<typeof createStaticToolLifecycleResultRenderer>[0]["createSpec"]>[0],
  state?: { expanded?: boolean },
) => ToolLifecycleSpec;

const taskRows = bindLifecycleRenderers({
  fit: truncateToWidth,
  visibleWidth,
  wrapDetail: (line, width) => wrapTextWithAnsi(line, Math.max(1, width)),
  expandHint: () => keyHint("app.tools.expand", "to expand"),
  hostComponent: ToolExecutionComponent,
});

/** Build the `renderResult` for one row spec. Injected into `registerTaskTools`
 *  so the tool library stays TUI-free and only the loaded entry paints. */
export function createTaskResultRenderer(spec: { createSpec: TaskRowSpec }): unknown {
  const expanded = taskRows.result(spec.createSpec);
  const collapsed = taskRows.result(result => spec.createSpec(result, { expanded: false }));
  return (...args: Parameters<typeof expanded>) => {
    const row = spec.createSpec(args[0]);
    // Lists contain titles, not hidden bodies. Wrap them in full by default.
    const list = row.label === "list";
    const renderer = args[1].expanded || list ? expanded : collapsed;
    return renderer(args[0], list ? { ...args[1], expanded: true } : args[1], args[2], args[3]);
  };
}

/** Paint only the status headline; full reminder content stays in model context. */
export function createTaskStatusRenderer(
  createSpec: (details: unknown) => ToolLifecycleSpec,
): Parameters<ExtensionAPI["registerMessageRenderer"]>[1] {
  return taskRows.message(message => createSpec(message.details));
}
