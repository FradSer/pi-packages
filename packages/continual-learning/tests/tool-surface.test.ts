import { expect, test } from "bun:test";
import {
  TOOL_NAMES,
  createParentToolSurface,
  type ToolSurfaceHost,
} from "../extensions/tool-surface.ts";

class FakeHost implements ToolSurfaceHost {
  activeTools: string[];

  constructor(activeTools: readonly string[] = []) {
    this.activeTools = [...activeTools];
  }

  getActiveTools(): string[] {
    return [...this.activeTools];
  }

  setActiveTools(names: string[]): void {
    this.activeTools = [...names];
  }
}

const PARENT_TOOLS = ["read", "bash", "edit", "write"];

test("parent learning activation preserves foreign tools", () => {
  const host = new FakeHost(PARENT_TOOLS);
  const surface = createParentToolSurface(host);

  surface.refreshAgentMemory(true);
  expect(host.activeTools).toEqual([...PARENT_TOOLS, TOOL_NAMES.learn]);

  surface.refreshAgentMemory(false);
  expect(host.activeTools).toEqual(PARENT_TOOLS);
});

test("Harness authoring activates and resets its declared tools", () => {
  const host = new FakeHost(["read", "write"]);
  const surface = createParentToolSurface(host);

  surface.beginHarnessAuthoring();
  expect(host.activeTools).toEqual(["read", "write", TOOL_NAMES.harnessPreview, TOOL_NAMES.harnessWrite]);

  surface.resetSession();
  expect(host.activeTools).toEqual(["read", "write"]);
});

test("retired worker loadouts and case tools are not exported", async () => {
  const module = await import("../extensions/tool-surface.ts");
  expect("workerCliArgs" in module).toBe(false);
  expect("WORKER_LOADOUTS" in module).toBe(false);
  expect("harnessCheckCases" in TOOL_NAMES).toBe(false);
  // The evidence marker and the collector's tool name survive.
  expect(TOOL_NAMES.learningRead).toBe("learning_read");
  expect(TOOL_NAMES.learn).toBe("learn");
});
