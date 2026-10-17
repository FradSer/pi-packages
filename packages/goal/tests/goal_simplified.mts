/** Given/When/Then regressions for the simplified thread Goal contract. */
import { observedAssert as assert, observeScenario, observedScenarios } from "../../../tests/e2e/support/assertion-observer.ts";
import { writeFileSync as writeObservationFile } from "node:fs";
import { existsSync, mkdtempSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import goalExtension from "../src/index.ts";
import { GoalCore, type GoalCoreOptions } from "../src/core.ts";
import { buildCheckPrompt } from "../src/check.ts";
import { refreshDashboard } from "../src/dashboard.ts";
import { writeProjectSettings, loadGoalSettings } from "../src/settings.ts";
import { goalRecordPath } from "../src/paths.ts";
import { validateToolArguments } from "@earendil-works/pi-ai";
import { isolatedAgentDir } from "./isolated-agent.mts";

isolatedAgentDir();

const results: string[] = [];
async function scenario(name: string, body: () => unknown) {
  try { await observeScenario(name, body); results.push(`ok ${name}`); }
  catch (error) { results.push(`FAIL ${name}: ${error instanceof Error ? error.message : String(error)}`); process.exitCode = 1; }
}
const theme = { fg: (_: string, s: string) => s, bg: (_: string, s: string) => s, bold: (s: string) => s };
function fixture(runCheck: GoalCoreOptions["runCheck"] = async () => ({ met: true, report: "Verified." }), host: { messageRenderers?: boolean } = {}) {
  const cwd = mkdtempSync(join(tmpdir(), "goal-simple-"));
  const tools = new Map<string, any>();
  const events = new Map<string, Function>();
  const renderers = new Map<string, Function>();
  const commands = new Map<string, any>();
  const branch: any[] = [];
  const sent: any[] = [];
  const notices: string[] = [];
  let widget: any;
  let busy = true;
  let pending = false;
  let aborted = 0;
  let refuseCheckpoint = false;
  let checkpointAttempts = 0;
  const pi = {
    on: (name: string, handler: Function) => events.set(name, handler),
    registerTool: (tool: any) => tools.set(tool.name, tool),
    registerCommand: (name: string, command: any) => commands.set(name, command),
    ...(host.messageRenderers === false ? {} : { registerMessageRenderer: (name: string, renderer: Function) => renderers.set(name, renderer) }),
    appendEntry: (customType: string, data: unknown) => branch.push({ type: "custom", customType, data }),
    sendMessage: (message: any, _options: any) => {
      // Counted before the refusal, so a retry of a refused delivery is visible.
      if (message.customType === "pi-goal-checkpoint") checkpointAttempts += 1;
      if (refuseCheckpoint && message.customType === "pi-goal-checkpoint") throw new Error("the host refused the checkpoint");
      sent.push(message); branch.push({ type: "custom_message", ...message });
    },
    getActiveTools: () => ["read", "bash"], getAllTools: () => [...tools.keys()].map(name => ({name})), setActiveTools() {},
  };
  const ctx = { cwd, mode: "tui", hasUI: true,
    ui: { notify: (message: string) => notices.push(message), select: async () => "Clear goal",
      setWidget: (_: string, factory: any) => { widget = factory ? factory({ requestRender() {} }, theme) : undefined; } },
    model: {provider: "fixture", id: "scripted"}, abort: async () => { aborted++; },
    isIdle: () => !busy, hasPendingMessages: () => pending,
    sessionManager: { getSessionId: () => "simple-thread", getBranch: () => branch },
  };
  goalExtension(pi as never, { projectRoot: cwd, runCheck });
  const core = (pi as any)._goalCore as GoalCore;
  core.restore(ctx as never);
  core.store.create({ id: "simple-goal", owner: "simple-thread", objective: "Export CSV." });
  core.focus("simple-goal", ctx as never, "created");
  const call = (name: string, args: unknown) => tools.get(name).execute("call", args, undefined, undefined, ctx);
  const fire = (name: string, event = {}) => events.get(name)?.(event, ctx);
  return { cwd, core, ctx, tools, events, branch, sent, notices, renderers, call, fire,
    command: (text: string) => commands.get("goal").handler(text, ctx),
    row: () => { refreshDashboard(core, ctx as never); return widget?.render(120).join("\n").trimEnd() ?? ""; },
    busy: (value: boolean) => {busy = value;}, pending: (value: boolean) => {pending = value;}, aborted: () => aborted,
    refuseCheckpoint: (value: boolean) => {refuseCheckpoint = value;},
    checkpointAttempts: () => checkpointAttempts,
    settle: async (predicate: () => boolean, seconds = 2) => {
      const deadline = Date.now() + seconds * 1000;
      while (!predicate()) {
        if (Date.now() > deadline) throw new Error("the condition was not reached in time");
        await new Promise(resolve => setTimeout(resolve, 5));
      }
    },
    arm: () => {
      const outcome = core.store.apply({ expectedGoalId: "simple-goal",
        mutate: goal => goal.scheduler ? { ...goal, scheduler: { ...goal.scheduler, phase: "ready" } } : undefined });
      assert.ok(outcome.ok, JSON.stringify(outcome));
      core.scheduler.schedule(core.goal!, {});
    },
    close: () => core.shutdown() };
}
async function use(body: (f: ReturnType<typeof fixture>) => unknown, check?: GoalCoreOptions["runCheck"], host?: { messageRenderers?: boolean }) {
  const f = fixture(check, host); try { await body(f); } finally { f.close(); }
}
await scenario("Given a loaded Goal extension When tools register Then only three Goal tools exist", () => use(f => {
  assert.deepEqual([...f.tools.keys()].sort(), ["create_goal", "get_goal", "update_goal"]);
}));
await scenario("Given completed work When settling Then no automatic checker is called", async () => {
  let checks = 0;
  await use(async f => {
    await f.fire("agent_start"); await f.fire("turn_start");
    await f.fire("tool_execution_end", {toolName: "write", isError: false, result: {}});
    await f.fire("agent_before_settle", {outcome: "completed"});
    assert.equal(checks, 0); assert.equal(f.core.goal?.status, "active");
  }, async () => {checks++; return {met: false, report: "Missing."};});
});
await scenario("Given valid completion When accepted Then keep the terminal record without creating archives", () => use(async f => {
  const archive = join(f.cwd, ".pi/goals/archived/legacy"); mkdirSync(archive, {recursive: true});
  writeFileSync(join(archive, "history.jsonl"), "legacy\n");
  const result = await f.call("update_goal", {status: "complete", completion_summary: "Tests passed."});
  assert.equal(result.isError, false); assert.equal(result.details.subject, "completed");
  assert.equal(f.core.goal, undefined);
  assert.equal(f.core.store.readGoal("simple-goal")?.status, "complete", "the finished record keeps its outcome");
  assert.ok(existsSync(goalRecordPath(f.cwd, "simple-goal")), "and is kept under the agent directory");
  assert.equal(existsSync(join(f.cwd, ".pi/goals/simple-goal/record.json")), false, "never inside the project");
  assert.equal(existsSync(join(f.cwd, ".pi/goals/archived/simple-goal")), false);
  assert.equal(readFileSync(join(archive, "history.jsonl"), "utf8"), "legacy\n");
  assert.doesNotMatch(result.content[0].text, /archiv/i);
}));
await scenario("Given a current goal When cleared Then end without completion or archive", () => use(async f => {
  await f.command("clear"); assert.equal(f.core.goal, undefined);
  assert.equal(f.core.store.readGoal("simple-goal")?.status, "complete", "clearing keeps the record");
  assert.ok(existsSync(goalRecordPath(f.cwd, "simple-goal")), "under the agent directory");
  assert.equal(existsSync(join(f.cwd, ".pi/goals")), false, "and writes nothing into the project");
  assert.ok(f.sent.some(m => m.details?.subject === "cleared"));
  assert.ok(!f.sent.some(m => /completed|archived/.test(m.content ?? "")));
}));
await scenario("Given busy CSV work When appending Windows requirement Then retain original until full revision", () => use(async f => {
  await f.command("Also validate Windows."); assert.equal(f.core.goal?.objective, "Export CSV.");
  const message = f.sent.at(-1); assert.match(message.content, /Also validate Windows/);
  await f.fire("message_start", {message: {role: "custom", ...message}});
  await f.call("update_goal", {objective: "Export CSV. Also validate Windows."});
  assert.equal(f.core.goal?.objective, "Export CSV. Also validate Windows.");
}));
await scenario("Given a long goal When constructing a check Then include its final requirement", () => {
  const text = buildCheckPrompt({objective: "Requirement. ".repeat(500) + "MANDATORY_TAIL", claim: undefined});
  assert.match(text, /MANDATORY_TAIL/); assert.doesNotMatch(text, /truncated at 4000/);
});
await scenario("Given three rejected completion requests When checking Then remain active", () => use(async f => {
  for(let i=0;i<3;i++) { await f.fire("turn_start"); const r=await f.call("update_goal", {status: "complete"}); assert.equal(r.details.subject,"not met"); }
  assert.equal(f.core.goal?.status,"active"); assert.equal(f.core.goal?.autoContinue,true);
}, async () => ({met:false,report:"Review missing."})));
await scenario("Given checker failure When completion requested Then report failure and wait without user pause", () => use(async f => {
  const r=await f.call("update_goal",{status:"complete"}); assert.equal(r.details.subject,"check failed");
  assert.equal(f.core.goal?.status,"active"); assert.match(f.row(), /Goal waiting/);
}, async () => ({met:false,report:"",error:"Provider unavailable."})));
await scenario("Given checker usage When result returns Then charge the Goal usage", () => use(async f => {
  await f.call("update_goal",{status:"complete"}); assert.equal(f.core.goal?.usage.tokensUsed,1234);
}, async () => ({met:false,report:"Review missing.",usage:{input:1000,output:234,cacheRead:0,cacheWrite:0,totalTokens:1234,cost:0}})));
await scenario("Given restored active state When no work is authorized Then show waiting", () => use(f => {
  assert.match(f.row(),/Goal waiting/); assert.doesNotMatch(f.row(),/Pursuing/);
}));
await scenario("Given running work When rendering footer Then keep Codex phrasing and elapsed time", () => use(async f => {
  f.core.store.apply({expectedGoalId:"simple-goal",mutate:d=>({...d,usage:{tokensUsed:0,activeSeconds:8700}})});
  await f.fire("agent_start"); assert.equal(f.row(),"Pursuing goal · 2h 25m");
}));
await scenario("Given an execution error When settling Then wait without autonomous user pause", () => use(async f => {
  await f.fire("agent_start"); await f.fire("agent_before_settle",{outcome:"failed"});
  assert.equal(f.core.goal?.status,"active"); assert.match(f.row(),/Goal waiting/);
}));
await scenario("Given repeated reads When each run settles Then stop repeated-output continuation", () => use(async f => {
  for(let i=0;i<2;i++) {
    await f.fire("agent_start"); await f.fire("turn_start");
    await f.fire("tool_execution_end",{toolName:"read",isError:false,result:{content:[{type:"text",text:"same source"}]}});
    await f.fire("agent_before_settle",{outcome:"completed"});
  }
  assert.equal(f.core.scheduler.isArmed(),false); assert.match(f.row(),/Goal waiting/);
}));
await scenario("Given novel reads When the change window fills Then stop autonomous continuation", () => use(async f=>{
  const read=async(i:number)=>{await f.fire("agent_start");await f.fire("tool_execution_end",{toolName:"read",isError:false,result:{content:[{type:"text",text:`source ${i}`}]},args:{path:`src/f${i}.ts`}});await f.fire("agent_before_settle",{outcome:"completed"});};
  await read(1); assert.equal(f.core.goal?.autoContinue,true,"two read-only runs are inside the window");
  await read(2); assert.equal(f.core.goal?.autoContinue,true);
  await read(3); assert.equal(f.core.goal?.autoContinue,false,"the third no-change run stops the loop");
  assert.match(f.core.goal?.pauseReason ?? "",/3 consecutive runs changed nothing observable/);
  assert.equal(f.core.goal?.scheduler?.phase,"idle","the stop drops any dispatch"); assert.match(f.row(),/Goal waiting/);
  await f.command("resume"); assert.equal(f.core.goal?.autoContinue,true,"resume starts the window again");
  await read(4); assert.equal(f.core.goal?.autoContinue,true);
  await read(5); await read(6); assert.equal(f.core.goal?.autoContinue,false);
}));
await scenario("Given a workspace change each run When the window fills Then keep continuing", () => use(async f=>{
  for(let i=0;i<5;i++){await f.fire("agent_start");await f.fire("tool_execution_start",{toolCallId:`w${i}`,toolName:"write",args:{path:`src/f${i}.ts`,content:`body ${i}`}});await f.fire("tool_execution_end",{toolCallId:`w${i}`,toolName:"write",isError:false,result:{content:[{type:"text",text:`wrote ${i}`}]}});await f.fire("agent_before_settle",{outcome:"completed"});}
  assert.equal(f.core.goal?.autoContinue,true,"every run changed the workspace");
  assert.equal(f.core.goal?.pauseReason,undefined);
  assert.equal(f.core.goal?.scheduler?.used,5,"every changed run was authorized");
}));
await scenario("Given a reworded objective between repeated reads When the window fills Then stop", () => use(async f=>{
  for(let i=0;i<3;i++){
    await f.call("update_goal",{objective:`Export CSV v${i}.`});
    await f.fire("agent_start");await f.fire("tool_execution_end",{toolName:"read",isError:false,result:{content:[{type:"text",text:"same source"}]},args:{path:"src/a.ts"}});
    await f.fire("agent_before_settle",{outcome:"completed"});
  }
  assert.equal(f.core.goal?.autoContinue,false,"a revision does not reset the change window");
  assert.match(f.core.goal?.pauseReason ?? "",/3 consecutive runs changed nothing observable/);
  assert.equal(f.core.goal?.scheduler?.phase,"idle");
}));
await scenario("Given a repeated edit after each objective revision When the window fills Then stop", () => use(async f=>{
  for(let i=0;i<4;i++){
    await f.call("update_goal",{objective:`Export CSV v${i}.`});
    await f.fire("agent_start");await f.fire("tool_execution_start",{toolCallId:`w${i}`,toolName:"write",args:{path:"src/a.ts",content:"same"}});await f.fire("tool_execution_end",{toolCallId:`w${i}`,toolName:"write",isError:false,result:{content:[{type:"text",text:"written"}]}});
    await f.fire("agent_before_settle",{outcome:"completed"});
  }
  assert.equal(f.core.goal?.autoContinue,false,"rewriting the same content is not progress");
  assert.match(f.core.goal?.pauseReason ?? "",/changed nothing observable/);
}));
await scenario("Given a user turn that only reads When it settles Then keep the change window", () => use(async f=>{
  for(let i=0;i<4;i++){
    await f.fire("message_start",{message:{role:"user",content:[{type:"text",text:`question ${i}`}]}});
    await f.fire("agent_start");await f.fire("tool_execution_end",{toolName:"read",isError:false,result:{content:[{type:"text",text:`source ${i}`}]},args:{path:`src/f${i}.ts`}});
    await f.fire("agent_before_settle",{outcome:"completed"});
  }
  assert.equal(f.core.goal?.autoContinue,true,"a user turn does not advance the window");
  assert.equal(f.core.goal?.scheduler?.used,4,"every user turn kept the loop");
}));
await scenario("Given a pause command When received Then abort current work and enforce the tool stop", () => use(async f => {
  await f.fire("turn_start"); await f.command("pause");
  assert.equal(f.aborted(),1); assert.equal(f.core.goal?.status,"paused");
  const guard=await f.fire("tool_call",{toolName:"bash"}); assert.equal(guard?.block,true);
}));
await scenario("Given an empty update When validating Then reject it without Nothing to record", () => use(async f => {
  assert.throws(()=>validateToolArguments(f.tools.get("update_goal"),{type:"toolCall",id:"bad",name:"update_goal",arguments:{}}));
  const r=await f.call("update_goal",{}); assert.equal(r.details.subject,"update not applied");
  assert.doesNotMatch(r.content[0].text,/Nothing to record|next action/);
}));
await scenario("Given an old history request When read Then direct to session history without ledger counts", () => use(async f => {
  const r=await f.call("get_goal",{section:"history"}); assert.doesNotMatch(r.content[0].text,/ledger events/);
  assert.match(r.content[0].text,/session/i);
}));
await scenario("Given project settings When saved Then load only supported runtime controls", () => use(f => {
  assert.ok(writeProjectSettings(f.cwd,{maxAutonomousRuns:2,provider:"fixture",model:"judge"}).ok);
  const settings=loadGoalSettings(f.cwd); assert.equal(settings.maxAutonomousRuns,2); assert.equal(settings.model,"judge");
}));
await scenario("Given caller cancellation When a check returns MET Then report cancellation without ending the goal", async () => {
  let release!: (result:{met:boolean;report:string})=>void;
  await use(async f=>{
    const abort=new AbortController();
    const pending=f.tools.get("update_goal").execute("cancel",{status:"complete"},abort.signal,undefined,f.ctx);
    abort.abort(); release({met:true,report:"Old result."});
    const r=await pending; assert.equal(r.details.subject,"check cancelled"); assert.ok(f.core.goal);
  },async ()=>new Promise(resolve=>{release=resolve;}));
});
await scenario("Given a revised objective When an older check returns MET Then discard the result", async () => {
  let release!: (result:{met:boolean;report:string})=>void;
  await use(async f=>{
    const pending=f.call("update_goal",{status:"complete"});
    await f.call("update_goal",{objective:"Export CSV and validate Windows."});
    release({met:true,report:"Old result."}); const r=await pending;
    assert.equal(r.details.subject,"check discarded"); assert.equal(f.core.goal?.objective,"Export CSV and validate Windows.");
  },async ()=>new Promise(resolve=>{release=resolve;}));
});
await scenario("Given three consecutive blocker turns When reported Then block without user pause", () => use(async f=>{
  for(let n=0;n<3;n++){await f.fire("turn_start"); const r=await f.call("update_goal",{status:"blocked",reason:"Missing external input."}); assert.equal(r.details.subject,n===2 ? "blocked" : "blocker reported");}
  assert.equal(f.core.goal?.status,"blocked"); assert.match(f.row(),/Goal blocked/);
}));
await scenario("Given repeated blocker calls in one turn When reported Then count only one turn", () => use(async f=>{
  await f.fire("turn_start"); for(let n=0;n<4;n++) await f.call("update_goal",{status:"blocked",reason:"Missing external input."});
  assert.equal(f.core.goal?.status,"active");
}));
await scenario("Given a blocker streak When new work or requirements arrive Then reset the streak", () => use(async f=>{
  for(let n=0;n<2;n++){await f.fire("turn_start");await f.call("update_goal",{status:"blocked",reason:"Missing external input."});}
  await f.fire("tool_execution_end",{toolName:"write",isError:false,result:{content:[{type:"text",text:"new content"}]}});
  await f.fire("turn_start"); const r=await f.call("update_goal",{status:"blocked",reason:"Missing external input."}); assert.equal(r.details.subject,"blocker reported");
  await f.call("update_goal",{objective:"Export CSV and validate Windows."}); await f.fire("turn_start");
  assert.equal((await f.call("update_goal",{status:"blocked",reason:"Missing external input."})).details.subject,"blocker reported");
}));
await scenario("Given spent tokens and runs When resuming Then preserve both totals", () => use(async f=>{
  f.core.store.apply({expectedGoalId:"simple-goal",mutate:d=>({...d,status:"paused",autoContinue:false,usage:{tokensUsed:123,activeSeconds:8700},scheduler:{...d.scheduler!,used:4}})});
  await f.command("resume"); assert.equal(f.core.goal?.usage.tokensUsed,123); assert.equal(f.core.goal?.usage.activeSeconds,8700); assert.equal(f.core.goal?.scheduler?.used,4);
  assert.match(f.row(),/Pursuing goal · 2h 25m/);
}));
await scenario("Given queued user input When productive work settles Then no boundary continuation is claimed", () => use(async f=>{
  await f.fire("agent_start"); await f.fire("tool_execution_end",{toolName:"write",isError:false,result:{}}); f.pending(true);
  const result=await f.fire("agent_before_settle",{outcome:"completed"}); assert.equal(result,undefined);
  assert.equal(f.core.goal?.scheduler?.used,0); assert.equal(f.core.scheduler.isArmed(),false);
}));
await scenario("Given new output When a read repeats Then allow meaningful work but stop identical output", () => use(async f=>{
  for(const [index,value] of ["before","after","after"].entries()){
    await f.fire("agent_start"); await f.fire("tool_execution_end",{toolName:"read",isError:false,result:{content:[{type:"text",text:value}]}});
    assert.equal(f.core.performedWork(),index < 2);
    await f.fire("agent_before_settle",{outcome:"completed"});
  }
  assert.equal(f.core.goal?.autoContinue,false);
}));
await scenario("Given a checker's usage When it returns MET Then charge it and complete", () => use(async f=>{
  const before=f.sent.length; const r=await f.call("update_goal",{status:"complete"}); assert.equal(r.details.subject,"completed");
  assert.equal(f.core.store.readGoal("simple-goal")?.usage.tokensUsed,1234,"the checker's own spend is charged");
  assert.equal(f.sent.length,before,"the tool owns this result, so no duplicate custom message is sent");
},async ()=>({met:true,report:"Verified.",usage:{input:1000,output:234,cacheRead:0,cacheWrite:0,totalTokens:1234,cost:0}})));
await scenario("Given a command result When rendering narrow Then use the same full band as tool results", () => use(async f=>{
  const tail="REASON_TAIL"; const reason="Keep every authored reason. ".repeat(100)+tail;
  f.core.store.apply({expectedGoalId:"simple-goal",mutate:d=>({...d,pauseReason:reason})}); await f.command("");
  const message=f.sent.at(-1); const command=f.renderers.get(message.customType)!(message,{expanded:false},theme).render(36).join("\n");
  const toolResult=await f.call("get_goal",{}); const tool=f.tools.get("get_goal").renderResult(toolResult,{expanded:false},theme,{}).render(36).join("\n");
  for(const text of [command,tool]){assert.match(text,/\[goal\] active/);assert.match(text,/REASON_TAIL/);assert.doesNotMatch(text,/to expand|…/);}
}));
await scenario("Given long checker error When rendered Then show one precise header and the full cause", () => use(async f=>{
  const result=await f.call("update_goal",{status:"complete"});
  const text=f.tools.get("update_goal").renderResult(result,{expanded:false},theme,{isError:true}).render(40).join("\n");
  assert.match(text,/\[goal\] check failed/); assert.match(text,/ERROR_TAIL/); assert.doesNotMatch(text,/failed · check failed|to expand/);
},async ()=>({met:false,report:"",error:"The provider could not finish. ".repeat(100)+"ERROR_TAIL"})));
await scenario("Given a failed setting delivery When revising later Then no request authorizes it", () => use(async f=>{
  f.core.store.apply({expectedGoalId:"simple-goal",mutate:d=>({...d,status:"paused",autoContinue:false})});
  f.core.pi.sendMessage=()=>{throw new Error("Delivery unavailable.");};
  await assert.rejects(()=>f.command("Also validate Windows."));
  await f.call("update_goal",{objective:"Export CSV. Also validate Windows."}); assert.equal(f.core.goal?.status,"paused");
}));

await scenario("Given pre-creation model usage When a Goal starts Then only its own usage counts", () => use(async f=>{
  await f.command("clear"); await f.fire("turn_start"); await f.fire("agent_start");
  await f.fire("message_end",{message:{role:"assistant",usage:{totalTokens:37},content:[{type:"toolCall",name:"create_goal"}]}});
  const r=await f.call("create_goal",{objective:"Run the CSV verification."});
  assert.equal(f.core.goal?.usage.tokensUsed,0,"the creating run's earlier turns are not charged to the new goal");
  assert.equal(f.core.goal?.status,"active"); assert.equal(r.details.subject,"started");
  assert.equal((await f.fire("tool_call",{toolName:"bash"})),undefined,"the creating turn keeps working");
}));
await scenario("Given an injected budget When a Goal starts Then no ceiling exists", () => use(async f=>{
  await f.command("clear");
  assert.equal(Object.keys(f.tools.get("create_goal").parameters.properties).includes("token_budget"),false,"the model has no way to ask for a spending limit");
  const r=await f.call("create_goal",{objective:"Run the CSV verification.",token_budget:250000});
  assert.equal(r.details.subject,"started"); assert.equal(f.core.goal?.status,"active","and an injected limit is ignored");
  await f.fire("agent_start"); await f.fire("message_end",{message:{role:"assistant",usage:{totalTokens:900000}}});
  assert.equal(f.core.goal?.autoContinue,true,"spending far past any earlier ceiling keeps the goal running");
}));
await scenario("Given a record an earlier version capped When it is read Then the ceiling is ignored", () => use(async f=>{
  const old=f.core.goal!;
  f.core.store.apply({expectedGoalId:old.id,mutate:d=>({...d,autoContinue:false,pauseReason:"The lifetime token cap of 10 tokens is spent."})});
  const legacy=JSON.parse(readFileSync(goalRecordPath(f.cwd,old.id),"utf8"));
  writeFileSync(goalRecordPath(f.cwd,old.id),JSON.stringify({...legacy,goal:{...legacy.goal,tokenBudget:10,usage:{...legacy.goal.usage,tokensUsed:10}}}));
  assert.equal(f.core.goal?.status,"active","a cap-era record still reads as this goal");
  assert.equal(f.core.goal?.usage.tokensUsed,10,"with its usage kept");
  await f.command("resume"); assert.equal(f.core.goal?.autoContinue,true,"and it resumes: nothing caps it");
}));
await scenario("Given accepted completion When returning Then terminate the run without another model call", () => use(async f=>{
  const result=await f.call("update_goal",{status:"complete"}); assert.equal(result.terminate,true);
  assert.equal((await f.fire("tool_call",{toolName:"bash"}))?.block,true);
}));
await scenario("Given a switched thread When cancelled checking returns usage Then charge the original open Goal", async () => {
  let release!: (value: any) => void;
  await use(async f => {
    const pending=f.call("update_goal",{status:"complete"});
    const other={...f.ctx,sessionManager:{getSessionId:()=>"other-thread",getBranch:()=>[]}};
    f.core.restore(other as never);
    release({met:false,cancelled:true,report:"Cancelled.",usage:{totalTokens:80}});
    await pending; assert.equal(f.core.store.readGoal("simple-goal")?.usage.tokensUsed,80);
  },()=>new Promise(resolve=>{release=resolve;}));
});
await scenario("Given accepted paused revision When its model responds Then account its usage",()=>use(async f=>{
  f.core.store.apply({expectedGoalId:"simple-goal",mutate:d=>({...d,status:"paused",autoContinue:false})});
  f.core.requestGoalActivation("revise"); f.core.acceptGoalSetting("revise");
  await f.fire("agent_start"); await f.fire("message_end",{message:{role:"assistant",usage:{totalTokens:90}}});
  assert.equal(f.core.goal?.usage.tokensUsed,90);
}));
await scenario("Given an unmet report When requirements or focus change Then clear the old report",()=>use(async f=>{
  f.core.setUnmet("Old private requirement missing."); f.core.requirementsChanged(); assert.equal(f.core.currentUnmet(),undefined);
  f.core.setUnmet("Old private requirement missing."); f.core.restore(f.ctx as never); assert.equal(f.core.currentUnmet(),undefined);
  f.core.setUnmet("Old private requirement missing."); await f.command("clear"); assert.equal(f.core.currentUnmet(),undefined);
}));
await scenario("Given an old-thread checker When cancelled usage returns Then charge its original Goal",async()=>{
  let release!: (value:any)=>void;
  await use(async f=>{
    const pending=f.call("update_goal",{status:"complete"});
    f.core.restore({...f.ctx,sessionManager:{getSessionId:()=>"other-thread",getBranch:()=>[]}} as never);
    release({met:false,cancelled:true,report:"Cancelled.",usage:{totalTokens:110}}); await pending;
    const old=f.core.store.readGoal("simple-goal")!; assert.equal(old.usage.tokensUsed,110); assert.equal(old.autoContinue,true,"and usage never stops it");
  },()=>new Promise(resolve=>{release=resolve;}));
});
await scenario("Given requirements revised before an error stop lock When old check fails Then discard without stopping new work",()=>use(async f=>{
  const apply=f.core.store.apply.bind(f.core.store); let intercept=true;
  f.core.store.apply=(spec)=>{
    if(intercept){ intercept=false; apply({expectedGoalId:"simple-goal",mutate:d=>({...d,objective:"New requirements.",evidenceSince:new Date(Date.now()+1).toISOString()})}); }
    return apply(spec);
  };
  const result=await f.call("update_goal",{status:"complete"});
  assert.equal(result.details.subject,"check discarded"); assert.equal(f.core.goal?.autoContinue,true);
  assert.equal((await f.fire("tool_call",{toolName:"bash"})),undefined);
},async()=>({met:false,report:"",error:"Old provider failure."})));
await scenario("Given an attributed model run When pause precedes its usage event Then still account returned tokens",()=>use(async f=>{
  await f.fire("agent_start"); await f.command("pause");
  await f.fire("message_end",{message:{role:"assistant",usage:{totalTokens:55}}});
  assert.equal(f.core.goal?.usage.tokensUsed,55); assert.equal(f.core.goal?.status,"paused");
}));
await scenario("Given an attributed model run When thread changes before usage Then charge only its original Goal",()=>use(async f=>{
  await f.fire("agent_start");
  f.core.restore({...f.ctx,sessionManager:{getSessionId:()=>"other-thread",getBranch:()=>[]}} as never);
  await f.fire("message_end",{message:{role:"assistant",usage:{totalTokens:55}}});
  assert.equal(f.core.store.readGoal("simple-goal")?.usage.tokensUsed,55);
}));
await scenario("Given overlapping thread messages When old usage ends after a new run Then keep original attribution",()=>use(async f=>{
  await f.fire("agent_start"); const old={role:"assistant",usage:{totalTokens:55}};
  await f.fire("message_start",{message:old});
  const other={...f.ctx,sessionManager:{getSessionId:()=>"other-thread",getBranch:()=>[]}};
  f.core.restore(other as never); f.core.store.create({id:"other-goal",owner:"other-thread",objective:"Other goal."}); f.core.focus("other-goal",other as never,"created");
  await f.events.get("agent_start")!({},other); await f.fire("message_end",{message:old});
  assert.equal(f.core.store.readGoal("simple-goal")?.usage.tokensUsed,55);
  assert.equal(f.core.store.readGoal("other-goal")?.usage.tokensUsed,0);
}));
await scenario("Given fenced Markdown with blank lines When rendering Then preserve authored code spacing", () => use(f => {
  const authored = "Before.\n\n```text\nFIRST_CODE_LINE\n\nLAST_CODE_LINE\n```\n\nAfter.";
  const result = {content:[{type:"text",text:authored}], details:{subject:"updated",summary:authored,markdown:true}};
  const lines = f.tools.get("get_goal").renderResult(result,{expanded:false},theme,{}).render(60).map((line:string)=>line.trimEnd());
  const first = lines.findIndex((line:string)=>line.includes("FIRST_CODE_LINE"));
  const last = lines.findIndex((line:string)=>line.includes("LAST_CODE_LINE"));
  assert.ok(first >= 0 && last > first + 1);
  assert.ok(lines.slice(first + 1,last).some((line:string)=>line.trim() === ""));
  assert.match(lines.join("\n"), /Before\./);
  assert.match(lines.join("\n"), /After\./);
}));
await scenario("Given a Goal-prefixed subject When rendering Then normalize only the transcript heading", () => use(f => {
  const result = {content:[{type:"text",text:"Goal updated\n\nFull report."}], details:{subject:"Goal updated",summary:"Full report."}};
  const rendered = f.tools.get("get_goal").renderResult(result,{expanded:false},theme,{}).render(60).join("\n");
  assert.match(rendered, /\[goal\] updated/);
  assert.doesNotMatch(rendered, /\[goal\] Goal/);
  assert.equal(result.details.subject, "Goal updated");
  assert.equal(result.content[0].text, "Goal updated\n\nFull report.");
}));
await scenario("Given successful transitions When delivering outcomes Then each has one visible result", () => use(async f => {
  const visible = () => f.sent.filter(message => message.display === true).length;
  const initial = visible();
  const pause = await f.call("update_goal",{status:"paused",reason:"User asked to wait."});
  assert.equal(pause.details.subject,"paused"); assert.equal(pause.content.length,1); assert.equal(visible(),initial);
  await f.command("resume");
  assert.equal(visible(),initial+1); assert.equal(f.sent.filter(message=>message.display===true).at(-1).details.subject,"resumed");
  const revised = await f.call("update_goal",{objective:"Export CSV with Windows verification."});
  assert.equal(revised.details.subject,"updated"); assert.equal(revised.content.length,1); assert.equal(visible(),initial+1);
  const complete = await f.call("update_goal",{status:"complete",completion_summary:"Verified."});
  assert.equal(complete.details.subject,"completed"); assert.equal(complete.content.length,1); assert.equal(visible(),initial+1);
  assert.equal(f.core.goal,undefined);
}));
await scenario("Given two blocker turns When restoring the thread Then restart the blocker audit", () => use(async f => {
  for(let n=0;n<2;n++){await f.fire("turn_start");await f.call("update_goal",{status:"blocked",reason:"Missing external input."});}
  f.core.restore(f.ctx as never); await f.fire("turn_start");
  const result = await f.call("update_goal",{status:"blocked",reason:"Missing external input."});
  assert.equal(result.details.subject,"blocker reported"); assert.equal(f.core.goal?.status,"active");
}));
await scenario("Given a successful turn with no tools When settling Then wait without pausing or continuing", () => use(async f => {
  await f.fire("agent_start"); await f.fire("turn_start");
  const before = f.sent.length;
  await f.fire("agent_before_settle",{outcome:"completed"});
  assert.ok(f.sent.slice(before).every(message=>message.customType === "goal-event" && message.details?.subject === "waiting")); assert.equal(f.core.goal?.status,"active");
  assert.equal(f.core.goal?.autoContinue,false); assert.equal(f.core.scheduler.isArmed(),false);
}));
await scenario("Given a paused Goal When accepting an explicit full revision Then authorize work and show pursuing", () => use(async f => {
  f.core.store.apply({expectedGoalId:"simple-goal",mutate:goal=>({...goal,status:"paused",autoContinue:false})});
  f.core.restore(f.ctx as never);
  assert.equal(f.core.goal?.status,"paused");
  await f.command("Also validate Windows.");
  const delivered = f.sent.at(-1);
  await f.fire("message_start",{message:{role:"custom",...delivered}});
  const result = await f.call("update_goal",{objective:"Export CSV. Also validate Windows."});
  assert.equal(result.details.subject,"updated");
  assert.equal(f.core.goal?.status,"active");
  assert.equal(f.core.scheduler.isArmed(),true);
  assert.match(f.row(),/Pursuing goal/);
  assert.doesNotMatch(f.row(),/Paused|Waiting/);
}));
await scenario("Given an explicit goal request When the command delivers it Then show one requesting row with the verbatim words", () => use(async f => {
  await f.command("Add Windows validation.");
  const delivered = f.sent.at(-1);
  assert.equal(delivered.customType,"goal-procedure");
  assert.equal(delivered.display,true,"the request row is a durable visible message");
  assert.equal(delivered.details.request,"Add Windows validation.");
  const rendered = f.renderers.get("goal-procedure")!(delivered,{},theme).render(80).join("\n");
  assert.match(rendered,/\[goal\] requesting/);
  assert.match(rendered,/Add Windows validation\./);
  assert.doesNotMatch(rendered,/Preserve all existing requirements/);
  assert.doesNotMatch(rendered,/to expand/);
  assert.equal((rendered.match(/\[goal\] requesting/g) ?? []).length,1,"one request row, not one per repaint");
}));
await scenario("Given a request carrying terminal escapes When the row renders Then keep only the plain words", () => use(async f => {
  await f.command("red\u001b[31mRED\u001b]0;OSC TITLE\u0007tail");
  const rendered = f.renderers.get("goal-procedure")!(f.sent.at(-1),{},theme).render(80).join("\n");
  assert.ok(!rendered.includes("\u001b"),"no escape byte survives into the row");
  assert.ok(!rendered.includes("\u0007"),"no bell byte survives into the row");
  assert.ok(!rendered.includes("OSC TITLE"),"no operating-system command survives into the row");
  assert.match(rendered,/red/); assert.match(rendered,/tail/);
}));
await scenario("Given a host without message renderers When the command delivers a request Then keep the body off the transcript", () => use(async f => {
  await f.command("Add Windows validation.");
  assert.equal(f.sent.at(-1).display,false,"no renderer means no visible row");
  assert.equal(f.renderers.size,0,"the host registers no renderer for this row");
}, undefined, { messageRenderers: false }));
await scenario("Given an armed decision When the host is idle Then deliver exactly one checkpoint for it", () => use(async f => {
  f.busy(false);
  const before = f.sent.length;
  f.arm();
  assert.equal(f.core.scheduler.isArmed(),true,"the decision is armed before delivery");
  await f.settle(() => f.core.store.readGoal("simple-goal")!.scheduler?.phase === "claimed");
  const delivered = f.sent.slice(before).filter(message => message.customType === "pi-goal-checkpoint");
  assert.equal(delivered.length,1,"one armed decision delivers exactly one checkpoint");
  assert.equal(f.checkpointAttempts(),1,"and it is attempted once");
  const goal = f.core.store.readGoal("simple-goal")!;
  assert.equal(goal.scheduler?.phase,"claimed","delivery claims the decision");
  assert.equal(delivered[0].details.goalId,goal.id);
  assert.equal(delivered[0].details.generation,goal.scheduler?.generation);
  assert.equal(delivered[0].details.dispatchId,goal.scheduler?.dispatch?.id);
  assert.equal(f.core.scheduler.isArmed(),false,"the claim spends the decision");
}));
await scenario("Given a claimed decision the host refuses to deliver When delivery fails Then stop the goal without replay", () => use(async f => {
  f.busy(false);
  f.refuseCheckpoint(true);
  const before = f.sent.length;
  f.arm();
  await f.settle(() => f.core.store.readGoal("simple-goal")!.autoContinue === false);
  const goal = f.core.store.readGoal("simple-goal")!;
  assert.equal(goal.autoContinue,false,"an undeliverable claim stops the loop");
  assert.equal(goal.stopReason,"agent");
  assert.match(goal.pauseReason ?? "",/could not be delivered/);
  assert.equal(goal.scheduler?.used,1,"the run was spent, not restored");
  assert.equal(f.core.scheduler.isArmed(),false);
  assert.equal(f.checkpointAttempts(),1,"the refused claim is attempted once and never replayed");
  assert.equal(f.sent.slice(before).filter(message => message.customType === "pi-goal-checkpoint").length,0,"no checkpoint reached the transcript");
  assert.ok(f.sent.slice(before).some(message => message.details?.subject === "waiting"),"the failure is reported once");
  assert.equal(f.core.scheduler.isRunning(),false);
  assert.match(f.row(),/Goal waiting/,"the footer reports the wait, not pursuit");
  assert.doesNotMatch(f.row(),/Pursuing goal/);
}));
console.log(JSON.stringify(results));

if (process.env.PI_E2E_ASSERTION_PATH) writeObservationFile(process.env.PI_E2E_ASSERTION_PATH, JSON.stringify(observedScenarios()));
