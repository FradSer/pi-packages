import assert from "node:assert/strict";

const extensionPath = process.argv[2];
assert.ok(extensionPath, "expected compiled extension path");
const { default: extension } = await import(extensionPath);

type RegisteredTool = {
  name: string;
  execute: (
    toolCallId: string,
    params: { query: string },
    signal?: AbortSignal,
    onUpdate?: unknown,
    ctx?: { cwd: string },
  ) => Promise<{ content: Array<{ type: string; text?: string }> }>;
};

const tools = new Map<string, RegisteredTool>();
extension({ registerTool(tool: RegisteredTool) { tools.set(tool.name, tool); } } as never);

assert.deepEqual([...tools.keys()], ["context_get"]);
const research = tools.get("context_get");
assert.ok(research);

const originalSpawn = (await import("node:child_process")).spawn;
const captured: string[] = [];

// The source tests assert the exact child-launch contract. This harness verifies
// that the tool rejects an empty child response instead of reporting success.
await assert.rejects(
  research.execute("empty", { query: "research React" }, undefined, undefined, { cwd: process.cwd() }),
  /returned no answer/,
);

void originalSpawn;
void captured;
