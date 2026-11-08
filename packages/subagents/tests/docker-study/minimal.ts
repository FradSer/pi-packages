/** One pass over each functional path. Real model, no provider stub. */
import fs from "node:fs";
import path from "node:path";
import { executeIntentTool } from "../../src/intent-tools.ts";
import { spawnResident, terminateAllAgents } from "../../src/spawner.ts";
import { listAgents } from "../../src/roster.ts";
import type { SessionNotice } from "../../src/session-result.ts";

const root = "/results";
const model = "magpie-hy4/hunyuan-eval/hy4-dev";
const notices: SessionNotice[] = [];
const waiters = new Map<string, (notice: SessionNotice) => void>();
const receipts: unknown[] = [];
const spawns: unknown[] = [];
const audit = path.resolve("/opt/study/packages/subagents/tests/docker-study/audit.ts");
const delivery = (notice: SessionNotice) => {
  notices.push(notice);
  fs.appendFileSync(`${root}/notices.jsonl`, JSON.stringify(notice) + "\n");
  if ("inputId" in notice && notice.inputId) waiters.get(notice.inputId)?.(notice);
};
function options(parent: string) {
  return { cwd: "/work", parentSessionId: parent, leaderModel: () => model, thinking: () => "off", deliverSessionResult: delivery,
    spawn: (input: Parameters<typeof spawnResident>[0]) => {
      const result = spawnResident({ ...input, extensions: [...(input.extensions ?? []), audit] });
      spawns.push({ name: input.agentName, session: input.session, sessionDir: input.sessionDir, tools: input.tools, result });
      fs.writeFileSync(`${root}/spawns.json`, JSON.stringify(spawns, null, 2));
      return result;
    } };
}
async function tool(name: Parameters<typeof executeIntentTool>[0], params: unknown, parent: string) {
  const result = await executeIntentTool(name, params, options(parent));
  receipts.push({ name, params, data: result.structuredContent, error: result.isError });
  fs.writeFileSync(`${root}/receipts.json`, JSON.stringify(receipts, null, 2));
  return result.structuredContent;
}
function settled(inputId: string): Promise<SessionNotice> {
  const existing = notices.find(n => "inputId" in n && n.inputId === inputId);
  if (existing) return Promise.resolve(existing);
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => { waiters.delete(inputId); reject(new Error(`Result deadline ${inputId}`)); }, 180000);
    waiters.set(inputId, n => { clearTimeout(timer); waiters.delete(inputId); resolve(n); });
  });
}
function definition(name: string, tools: string[]) {
  const dir = `/agent/agents/${name}`;
  fs.mkdirSync(dir, { recursive: true });
  fs.writeFileSync(`${dir}/agent.md`, `---\nname: ${name}\ndescription: Compact contract probe.\ntools: ${tools.join(", ")}\n---\nFollow the exact instruction. Keep answers to one word.\n`);
}
async function run(params: Record<string, unknown>, parent: string) {
  const data = await tool("agent_start", params, parent);
  if (!data.ok || !data.session || !data.inputId) throw new Error(`Start refused: ${JSON.stringify(data)}`);
  const notice = await settled(data.inputId);
  const stop = await tool("agent_stop", { session: data.session }, parent);
  return { data, notice, stop };
}
const report: Record<string, unknown> = { model, piVersion: JSON.parse(fs.readFileSync("/opt/study/node_modules/@earendil-works/pi-coding-agent/package.json", "utf8")).version };
function save() { fs.writeFileSync(`${root}/study.json`, JSON.stringify(report, null, 2)); }
try {
  // 1. Temporary role: start, next, list, stop, stale handle.
  const started = await tool("agent_start", { label: "temporary", tools: [], prompt: "Reply exactly FIRST_OK." }, "temporary");
  if (!started.ok || !started.session || !started.inputId) throw new Error(JSON.stringify(started));
  const first = await settled(started.inputId);
  const next = await tool("agent_input", { session: started.session, prompt: "Reply exactly SECOND_OK.", delivery: "next" }, "temporary");
  if (!next.inputId) throw new Error(JSON.stringify(next));
  const second = await settled(next.inputId);
  const list = await tool("agent_list", {}, "temporary");
  const idle = listAgents().find(a => a.spawnId === started.session!.split(":").at(-1))?.status;
  const stop = await tool("agent_stop", { session: started.session }, "temporary");
  const stale = await tool("agent_input", { session: started.session, prompt: "MUST_NOT_RUN", delivery: "next" }, "temporary");
  report.temporary = { started, first, next, second, list, idle, stop, stale }; save();

  // 2. Saved identity: start, steer, stop, restart with history, invalid identities.
  definition("resident", ["read", "agent_memory"]);
  const savedStart = await tool("agent_start", { identity: "resident", tools: [], prompt: "Reply exactly SAVED_OK." }, "saved");
  if (!savedStart.ok || !savedStart.session || !savedStart.inputId) throw new Error(JSON.stringify(savedStart));
  const steer = await tool("agent_input", { session: savedStart.session, prompt: "Answer SAVED_OK only.", delivery: "steer" }, "saved");
  const savedNotice = await settled(savedStart.inputId);
  const savedStop = await tool("agent_stop", { session: savedStart.session }, "saved");
  const restart = await run({ identity: "resident", tools: [], prompt: "What exact reply did you give before this one? Return only that reply or UNKNOWN." }, "saved");
  report.saved = { started: savedStart, steer, notice: savedNotice, stop: savedStop, restart }; save();
  report.invalidIdentity = await tool("agent_start", { identity: "not-defined", prompt: "MUST_NOT_RUN" }, "invalid");
  report.identityWithInstructions = await tool("agent_start", { identity: "resident", instructions: "override", prompt: "MUST_NOT_RUN" }, "invalid");
  save();

  // 3. Read-only Memory: append refused, propose accepted as unaccepted candidate.
  const memoryParams = { name: "probe", description: "Compact probe.", body: "Observed contract." };
  const readonlyStart = await tool("agent_start", { identity: "resident", tools: ["read", "agent_memory"],
    prompt: `This is a contract probe. Call agent_memory twice, both with arguments ${JSON.stringify(memoryParams)}: first action append, then action propose. The first call is expected to be refused by policy, the second accepted as a candidate. Reply PROBE_DONE.` }, "memory-readonly");
  if (!readonlyStart.ok || !readonlyStart.session || !readonlyStart.inputId) throw new Error(JSON.stringify(readonlyStart));
  const readonlyNotice = await settled(readonlyStart.inputId);
  const readonlyStop = await tool("agent_stop", { session: readonlyStart.session }, "memory-readonly");
  const readonly = { data: readonlyStart, notice: readonlyNotice, stop: readonlyStop };
  const proposals = fs.existsSync("/agent/agents/resident/memory/proposals") ? fs.readdirSync("/agent/agents/resident/memory/proposals") : [];
  report.readonly = { ...readonly, proposals }; save();

  // 4. Write-granted Memory: model appends one entry; index is injected on next input.
  definition("writer", ["read", "write", "agent_memory"]);
  const writerStart = await tool("agent_start", { identity: "writer", tools: ["read", "agent_memory", "write"],
    prompt: 'Call agent_memory action append with name "contract", description "Compact contract.", body "Compare runtime reads with packed files." Then reply APPEND_OK.' }, "memory-writer");
  if (!writerStart.ok || !writerStart.session || !writerStart.inputId) throw new Error(JSON.stringify(writerStart));
  const writerFirst = await settled(writerStart.inputId);
  const writerNext = await tool("agent_input", { session: writerStart.session,
    prompt: "Reply exactly INDEX_OK.", delivery: "next" }, "memory-writer");
  if (!writerNext.inputId) throw new Error(JSON.stringify(writerNext));
  const writerSecond = await settled(writerNext.inputId);
  const writerStop = await tool("agent_stop", { session: writerStart.session }, "memory-writer");
  const memoryDir = "/agent/agents/writer/memory";
  const memoryFiles = fs.existsSync(memoryDir) ? fs.readdirSync(memoryDir).filter(f => f.endsWith(".md"))
    .map(f => ({ file: f, body: fs.readFileSync(`${memoryDir}/${f}`, "utf8") })) : [];
  report.writer = { started: writerStart, first: writerFirst, next: writerNext, second: writerSecond, stop: writerStop, memoryFiles }; save();

  report.finalRoster = listAgents().map(a => ({ name: a.name, status: a.status }));
  report.completed = true; save();
} catch (error) { report.error = error instanceof Error ? error.stack : String(error); save(); process.exitCode = 1; }
finally { report.closure = await terminateAllAgents(); save(); }
