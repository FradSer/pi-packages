import { setOwnedTools } from "@fradser/pi-kit";

/** Canonical names for the tools the package registers. `learning_read` is
 * also the frozen-dossier evidence marker and the collector's scoped tool. */
export const TOOL_NAMES = {
  learn: "learn",
  harnessPreview: "harness_preview",
  harnessWrite: "harness_write",
  learningRead: "learning_read",
} as const;

export interface ToolSurfaceHost {
  getActiveTools(): string[];
  setActiveTools(names: string[]): void;
}

export interface ParentToolSurface {
  refreshAgentMemory(enabled: boolean): void;
  beginHarnessAuthoring(): void;
  resetSession(): void;
}

/** The dynamic current-source collector's single scoped read tool. It is the
 * only worker-side tool surface left; planner children run with --no-tools. */
export interface CollectorToolSurface {
  sessionStart(): void;
  noteRead(): boolean;
  beforeProviderRequest(event: unknown, ctx: unknown): Record<string, unknown> | undefined;
}

interface CollectorHost {
  getActiveTools?(): string[];
  setActiveTools(names: string[]): void;
}

function disclosure(host: unknown): ToolSurfaceHost | undefined {
  if (!host || typeof host !== "object") return undefined;
  const candidate = host as Partial<ToolSurfaceHost>;
  return typeof candidate.getActiveTools === "function" && typeof candidate.setActiveTools === "function"
    ? candidate as ToolSurfaceHost
    : undefined;
}

function collectorDisclosure(host: unknown): CollectorHost | undefined {
  if (!host || typeof host !== "object") return undefined;
  const candidate = host as Partial<CollectorHost>;
  return typeof candidate.setActiveTools === "function"
    ? candidate as CollectorHost
    : undefined;
}

function activateTool(host: ToolSurfaceHost, name: string): void {
  host.setActiveTools([...new Set([...host.getActiveTools(), name])]);
}

function deactivateTool(host: ToolSurfaceHost, name: string): void {
  host.setActiveTools(host.getActiveTools().filter(tool => tool !== name));
}

const inertParentSurface: ParentToolSurface = {
  refreshAgentMemory() {},
  beginHarnessAuthoring() {},
  resetSession() {},
};

export function createParentToolSurface(host: unknown): ParentToolSurface {
  const tools = disclosure(host);
  if (!tools) return inertParentSurface;
  return {
    refreshAgentMemory(enabled) {
      setOwnedTools(tools, {
        owned: [TOOL_NAMES.learn],
        toggled: [TOOL_NAMES.learn],
        enabled,
      });
    },
    beginHarnessAuthoring() {
      activateTool(tools, TOOL_NAMES.harnessPreview);
      activateTool(tools, TOOL_NAMES.harnessWrite);
    },
    resetSession() {
      deactivateTool(tools, TOOL_NAMES.harnessPreview);
      deactivateTool(tools, TOOL_NAMES.harnessWrite);
    },
  };
}

function inertCollectorSurface(): CollectorToolSurface {
  return {
    sessionStart() {},
    noteRead() { return false; },
    beforeProviderRequest() { return undefined; },
  };
}

/** Read-budget surface for the retained current-source collector only. It
 * registers just learning_read; no planner loadout, case tool or CLI allowlist
 * remains. `maxReads` is the collector's verified cancellation-prefix bound. */
export function createCollectorToolSurface(
  host: unknown,
  options: { maxReads?: number } = {},
): CollectorToolSurface {
  const tools = collectorDisclosure(host);
  if (!tools) return inertCollectorSurface();
  const maxReads = options.maxReads;
  const readHostActiveTools = tools.getActiveTools;
  // Do not read Pi's disclosure state while the generated extension is loading;
  // action methods are unavailable until the runtime is initialized.
  let fallbackActiveTools: string[] = [];
  const readActive = (): string[] => typeof readHostActiveTools === "function"
    ? [...readHostActiveTools.call(tools)]
    : [...fallbackActiveTools];
  const writeActive = (names: string[]): void => {
    fallbackActiveTools = [...names];
    tools.setActiveTools(names);
  };
  let reads = 0;
  return {
    sessionStart() {
      writeActive([TOOL_NAMES.learningRead]);
    },
    noteRead() {
      reads += 1;
      if (maxReads !== undefined && reads >= maxReads) writeActive([]);
      return maxReads !== undefined && reads > maxReads;
    },
    beforeProviderRequest(event, ctx): Record<string, unknown> | undefined {
      if (maxReads === undefined || reads < maxReads || readActive().length !== 0) return undefined;
      const model = (ctx as { model?: { api?: unknown } } | undefined)?.model;
      if (model?.api !== "openai-completions") return undefined;
      const payload = (event as { payload?: unknown } | undefined)?.payload;
      if (!payload || typeof payload !== "object" || Array.isArray(payload)) return undefined;
      const request = payload as Record<string, unknown>;
      if (!Array.isArray(request.messages)
        || request.tools !== undefined && (!Array.isArray(request.tools) || request.tools.length !== 0)) return undefined;
      // Past tool calls remain as evidence; an empty definition list alone can
      // still make some providers request unavailable tools repeatedly.
      return { ...request, tool_choice: "none" };
    },
  };
}
