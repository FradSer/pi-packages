import fs from "node:fs";
import path from "node:path";
import type { ExtensionAPI, ExtensionContext, ExtensionEvent, ToolDefinition } from "@earendil-works/pi-coding-agent";
import { assistant } from "./automatic-results-fixture.ts";
import { readJsonlBatch, readRoster, writeBoardFile, writeRoster } from "../src/statefile.ts";
import { registerWorkerCapabilities, workerBinding } from "../src/worker.ts";

export { assistant };

export function createAttemptFixture(root: string, kind: "direct" | "board" | "none" = "direct") {
  Object.assign(process.env, {
    PI_TEAMMATE_WORKER_NAME: "worker", PI_TEAMMATE_SPAWN_ID: "spawn-1",
    PI_TEAMMATE_OUTBOX_FILE: `${root}/events.jsonl`, PI_TEAMMATE_INBOX_FILE: `${root}/mail/inbox-worker.jsonl`,
    PI_TEAMMATE_ROSTER_FILE: `${root}/roster.json`, PI_TEAMMATE_BOARD_FILE: `${root}/board.json`,
    PI_TEAMMATE_CLAIMS_DIR: `${root}/claims`, PI_TEAMMATE_SUBMISSIONS_DIR: `${root}/submissions`,
  });
  const binding = workerBinding()!;
  writeRoster(binding.rosterFile, [
    { name: "worker", agent: "reviewer", spawnId: "spawn-1", status: "working",
      ...(kind === "none" ? {} : { currentTaskId: "work-1", assignment: { id: "attempt-1", kind, resources: [] } }) },
    { name: "peer", agent: "reader", spawnId: "peer-1", status: "idle" },
  ]);
  const task = (id: string, status: "claimed" | "pending") => ({
    id, subject: id, status, dependsOn: [], resources: [], createdAt: 1, updatedAt: 1,
    ...(status === "claimed" ? { claimedBy: "worker" } : {}),
  });
  writeBoardFile(binding.boardFile, { "work-1": task("work-1", "claimed"), "work-2": task("work-2", "pending") });
  type Handler = (event: ExtensionEvent, ctx: ExtensionContext) => unknown;
  const hooks = new Map<string, Handler[]>();
  const tools = new Map<string, ToolDefinition>();
  let active = ["read", "work", "agent_event"];
  const pi: Pick<ExtensionAPI, "on" | "registerTool" | "getActiveTools" | "setActiveTools"> = {
    on(event, handler) { hooks.set(event, [...(hooks.get(event) ?? []), handler as Handler]); },
    registerTool(tool) { tools.set(tool.name, tool as unknown as ToolDefinition); },
    getActiveTools: () => [...active], setActiveTools(names) { active = [...names]; },
  };
  const ctx = { isIdle: () => true } as ExtensionContext;
  const disclosure = registerWorkerCapabilities(pi as ExtensionAPI);
  const emit = async (event: ExtensionEvent) => {
    for (const handler of hooks.get(event.type) ?? []) await handler(event, ctx);
  };
  const prompt = async (text: string, timestamp = 10) => {
    // Mirrors index.ts's before_agent_start hook, then Pi's user-message event.
    disclosure.update(text);
    await emit({ type: "message_start", message: { role: "user", content: text, timestamp } });
  };
  return {
    binding, disclosure, emit, prompt,
    active: () => [...active],
    self: () => readRoster(binding.rosterFile)[0]!,
    patch(patch: Partial<ReturnType<typeof readRoster>[number]>) {
      const roster = readRoster(binding.rosterFile);
      Object.assign(roster[0]!, patch);
      writeRoster(binding.rosterFile, roster);
    },
    records: () => readJsonlBatch(binding.outbox, 0).records,
    peerRecords: () => readJsonlBatch(path.join(root, "mail", "inbox-peer.jsonl"), 0).records,
    intents: (dir = binding.submissionsDir) => fs.existsSync(dir) ? fs.readdirSync(dir).map(file => JSON.parse(fs.readFileSync(path.join(dir, file), "utf8"))) : [],
    start: (id = "attempt-1", timestamp = 10) => prompt(`[agent-teams-assignment:${id}]\nDo this assignment`, timestamp),
    answer: async (message: ReturnType<typeof assistant>) => {
      await emit({ type: "message_start", message: { ...message, stopReason: "pending" } });
      await emit({ type: "message_end", message });
    },
    call: (name: string, params: object) => tools.get(name)!.execute("call", params, undefined, undefined, ctx),
  };
}
