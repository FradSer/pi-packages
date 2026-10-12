/**
 * Terminal geometry for the `task` tool's lifecycle row.
 *
 * One binding, resolved once, shared by every `task` result this package paints:
 * the same shared band every other tool in this workspace uses, rather than a
 * fourth row shape to keep in step.
 *
 * Results and automatic messages share one geometry binding.
 * Waiting messages use the native host for expansion and input ownership.
 */

import { keyHint, ToolExecutionComponent, type ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { truncateToWidth, visibleWidth, wrapTextWithAnsi } from "@earendil-works/pi-tui";
import {
  bindLifecycleRenderers,
  type LifecycleRendererBindings,
  type createStaticToolLifecycleResultRenderer,
  type ToolLifecycleSpec,
} from "@fradser/pi-kit";
import { taskDisplayIndex, taskDisplayReference } from "./display.ts";
import { listTasks } from "./store.ts";

/** The spec builder the tool hands in; the binding supplies the geometry.
 *  Expansion state reaches the renderer through the host render call, never
 *  through this builder, so the builder takes the result alone. */
export type TaskRowSpec = (
  result: Parameters<Parameters<typeof createStaticToolLifecycleResultRenderer>[0]["createSpec"]>[0],
) => ToolLifecycleSpec;

const lifecycleGeometry: Pick<LifecycleRendererBindings, "fit" | "visibleWidth" | "wrapDetail"> = {
  fit: truncateToWidth,
  visibleWidth,
  wrapDetail: (line, width) => wrapTextWithAnsi(line, Math.max(1, width)),
};

const taskRows = bindLifecycleRenderers({
  ...lifecycleGeometry,
  expandHint: () => keyHint("app.tools.expand", "to expand"),
  hostComponent: ToolExecutionComponent,
});



/** Build the `renderResult` for one row spec. Injected into `registerTaskTools`
 *  so the tool library stays TUI-free and only the loaded entry paints.
 *
 *  A refusal is the same bound band as a success, so it carries the native key
 *  hint and the same expansion mechanism. It only replaces the spec: the label
 *  names the action that did not apply, and the error tone marks the band. */
export function createTaskResultRenderer(spec: { createSpec: TaskRowSpec }): unknown {
  const renderer = taskRows.result(spec.createSpec);
  const errorRenderer = taskRows.result((result: TaskRowResult) => errorSpecFor(spec, result));
  return (...args: Parameters<typeof renderer>) => args[3].isError
    ? errorRenderer(errorResultForDisplay(args[0]), args[1], args[2], { isError: false })
    : renderer(args[0], args[1], args[2], args[3]);
}

type TaskRowResult = Parameters<TaskRowSpec>[0];

function errorSpecFor(spec: { createSpec: TaskRowSpec }, result: TaskRowResult): ToolLifecycleSpec {
  const value = result as { content?: {text?: string}[]; details?: {tool?: string; task?: unknown} };
  const action = value.details?.tool?.replace(/_tasks?$/, "") ?? "update";
  const taskSpec = spec.createSpec(result);
  const text = (value.content ?? []).map(part => part.text ?? "");
  return {
    ...taskSpec, kind: "event", label: `${action} not applied`, tone: "error",
    subject: value.details?.task ? taskSpec.subject : "",
    summary: value.details?.task ? [...text, ...(taskSpec.summary ?? [])] : taskSpec.summary,
    expandedSummary: true, verbatimSubject: true, details: [],
  };
}

function errorResultForDisplay<T>(result: T): T {
  const value = result as { content?: unknown };
  if (!Array.isArray(value.content)) return result;
  const tasks = listTasks();
  const index = taskDisplayIndex(tasks);
  const labels = new Map(tasks.map(task => [task.id, taskDisplayReference(task.id, index)]));
  const content = value.content.map(part => {
    if (!part || typeof part !== "object" || typeof (part as { text?: unknown }).text !== "string") return part;
    let text = (part as { text: string }).text;
    text = text.replace(/\b[Tt]ask "([^"]+)"/g, (_match, id: string) => {
      const label = labels.get(id);
      return label ? `Task "${label}"` : "Task not found";
    });
    text = text.replace(/"([^"]+)"/g, (match, id: string) => {
      const label = labels.get(id);
      return label ? `"${label}"` : match;
    });
    text = text
      .replace(/Task not found does not exist\./gi, "The task does not exist.")
      .replace(/Unknown task id in (dependsOn|supersedes): [^\r\n]+\.$/gim, (_match, field: string) => (
        field === "dependsOn" ? "A dependency refers to a task that does not exist." : "A replacement refers to a task that does not exist."
      ));
    return { ...(part as Record<string, unknown>), text };
  });
  return { ...(result as object), content } as T;
}

/** Paint task data with native expansion; keep harness instructions in model context. */
export function createTaskStatusRenderer(
  createSpec: (details: unknown) => ToolLifecycleSpec,
): Parameters<ExtensionAPI["registerMessageRenderer"]>[1] {
  return taskRows.message(message => createSpec(message.details));
}
