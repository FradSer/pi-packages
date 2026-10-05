import { mock } from "bun:test";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
const root = fs.mkdtempSync(path.join(os.tmpdir(), "learning-preparation-"));
const cwd = path.join(root, "project"), agent = path.join(root, "agent");
process.env.PI_CODING_AGENT_DIR = agent;
fs.mkdirSync(cwd); fs.mkdirSync(path.join(agent, "memory"), { recursive: true });
const scenario = process.argv[2];
fs.writeFileSync(path.join(agent, "memory", "settings.json"), scenario === "invalid-settings" ? "{" : JSON.stringify({ autoMemory: !scenario.startsWith("disabled") }));
const entries = [{ id: "task1", message: { role: "user", content: scenario === "freeze" || scenario.startsWith("shutdown") ? "Inspect original task evidence." : "I prefer original task evidence." } }, { id: "result1", message: { role: "assistant", content: "Acknowledged." } }];
if (scenario === "disabled-later") entries.unshift({id:"older",message:{role:"user",content:"Inspect the previous task."}},entries[1]);
const session = path.join(root, "session.jsonl");
fs.writeFileSync(session, [JSON.stringify({ type: "session", cwd }), ...entries.map(entry => JSON.stringify(entry))].join("\n") + "\n");
const kit = await import("../../kit/src/index.ts");
const prompts: string[] = [];
mock.module("../../kit/src/index.ts", () => ({ ...kit,
  runPiWorker: async ({ prompt }: { prompt: string }) => { prompts.push(prompt); return {exitCode:0,stderr:"",text:JSON.stringify({kind:"incremental-memory-selection",version:1,contextDigest:/Context digest: ([a-f0-9]+)/.exec(prompt)![1],selected:[],memory:false,harness:false,agents:false,reason:"no durable delta"})}; },
  spawnPiChild: () => { throw new Error("No planner expected"); },
}));
const consolidation = await import("../extensions/consolidation-run.ts");
const acquire = consolidation.acquireConsolidationLock;
let preparing = false, release: () => void = () => {}, ready: () => void = () => {};
const gate = new Promise<void>(resolve => { release = resolve; });
const entered = new Promise<void>(resolve => { ready = resolve; });
mock.module("../extensions/consolidation-run.ts", () => ({ ...consolidation,
  acquireConsolidationLock: async (...args: Parameters<typeof consolidation.acquireConsolidationLock>) => {
    const lock = await acquire(...args);
    if (preparing) { preparing = false; ready(); await gate; }
    return lock;
  },
}));
const efficiency = await import("../extensions/learning-efficiency.ts");
const writeReceipt = efficiency.writeLearningReceipt;
mock.module("../extensions/learning-efficiency.ts", () => ({ ...efficiency,
  writeLearningReceipt: async (...args: Parameters<typeof writeReceipt>) => {
    if (scenario.endsWith("receipt")) { ready(); await gate; }
    return writeReceipt(...args);
  },
}));
try {
  const { default: register } = await import("../extensions/inject-memory.ts");
  const { backlogStatus, readBacklog, backlogFile } = await import("../extensions/learning-backlog.ts");
  const hooks = new Map<string, Array<(event: unknown, ctx: unknown) => unknown>>(), commands = new Map();
  const notices: string[] = [];
  let reported = 0;
  register({on:(name,fn)=>hooks.set(name,[...(hooks.get(name)??[]),fn]),registerCommand:(name,command)=>commands.set(name,command),getCommands:()=>[],registerMessageRenderer:()=>{},sendMessage:()=>{reported += 1;},appendEntry:()=>{},registerEntryRenderer:()=>{}} as Parameters<typeof register>[0]);
  const ctx={cwd,mode:"json",hasUI:false,ui:{notify:(text:string)=>notices.push(text),setWidget:()=>{}},sessionManager:{getBranch:()=>entries,buildContextEntries:()=>entries,getSessionFile:()=>session}};
  const emit=async(name:string,event:unknown={})=>{for(const fn of hooks.get(name)??[])await fn(event,ctx)};
  await emit("session_start");
  if (scenario.endsWith("receipt")) {
    await emit("input",{source:"interactive"});
    const run = scenario === "shutdown-zero-receipt" ? emit("agent_settled") : commands.get("consolidate").handler("",ctx);
    await entered;
    const shutdown = emit("session_shutdown");
    release(); await run; await shutdown;
  } else if (scenario === "freeze" || scenario === "shutdown") {
    preparing=true; const run=commands.get("consolidate").handler("",ctx); await entered;
    let shutdown: Promise<void> | undefined;
    if(scenario === "freeze") entries[0].message.content="Inspect replacement task evidence.";
    else shutdown=emit("session_shutdown");
    release();await run;if(shutdown)await shutdown;
  } else {
    await emit("input",{source:"interactive"});await emit("agent_settled");await emit("agent_settled");
  }
  if(scenario === "disabled-status") await commands.get("memory").handler("status",ctx);
  if(scenario === "disabled-corrupt-status") {
    fs.writeFileSync(backlogFile(cwd), "{\n");
    await commands.get("memory").handler("status",ctx);
    await commands.get("consolidate").handler("backfill",ctx);
  }
  await emit("session_shutdown");
  const paths=consolidation.resolveConsolidationRunPaths(cwd);
  console.log(JSON.stringify({selectors:prompts.length,original:prompts.every(prompt=>prompt.includes("original task evidence")),replacement:prompts.some(prompt=>prompt.includes("replacement task evidence")),lock:fs.existsSync(paths.lockFile),reported,notices,backlog:backlogStatus(cwd),entries:readBacklog(cwd).entries}));
} finally {fs.rmSync(root,{recursive:true,force:true});}
