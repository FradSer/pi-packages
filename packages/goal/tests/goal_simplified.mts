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
import { validateToolArguments } from "@earendil-works/pi-ai";

const results: string[] = [];
async function scenario(name: string, body: () => unknown) {
  try { await observeScenario(name, body); results.push(`ok ${name}`); }
  catch (error) { results.push(`FAIL ${name}: ${error instanceof Error ? error.message : String(error)}`); process.exitCode = 1; }
}
const theme = { fg: (_: string, s: string) => s, bg: (_: string, s: string) => s, bold: (s: string) => s };
function fixture(runCheck: GoalCoreOptions["runCheck"] = async () => ({ met: true, report: "Verified." })) {
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
  const pi = {
    on: (name: string, handler: Function) => events.set(name, handler),
    registerTool: (tool: any) => tools.set(tool.name, tool),
    registerCommand: (name: string, command: any) => commands.set(name, command),
    registerMessageRenderer: (name: string, renderer: Function) => renderers.set(name, renderer),
    appendEntry: (customType: string, data: unknown) => branch.push({ type: "custom", customType, data }),
    sendMessage: (message: any, _options: any) => { sent.push(message); branch.push({ type: "custom_message", ...message }); },
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
  core.store.create({ id: "simple-goal", owner: "simple-thread", objective: "Export CSV.", contract: "CSV E2E passes." });
  core.focus("simple-goal", ctx as never, "created");
  const call = (name: string, args: unknown) => tools.get(name).execute("call", args, undefined, undefined, ctx);
  const fire = (name: string, event = {}) => events.get(name)?.(event, ctx);
  return { cwd, core, ctx, tools, events, branch, sent, notices, renderers, call, fire,
    command: (text: string) => commands.get("goal").handler(text, ctx),
    row: () => { refreshDashboard(core, ctx as never); return widget?.render(120).join("\n").trimEnd() ?? ""; },
    busy: (value: boolean) => {busy = value;}, pending: (value: boolean) => {pending = value;}, aborted: () => aborted,
    close: () => core.shutdown() };
}
async function use(body: (f: ReturnType<typeof fixture>) => unknown, check?: GoalCoreOptions["runCheck"]) {
  const f = fixture(check); try { await body(f); } finally { f.close(); }
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
await scenario("Given valid completion When accepted Then release runtime record without creating archives", () => use(async f => {
  const archive = join(f.cwd, ".pi/goals/archived/legacy"); mkdirSync(archive, {recursive: true});
  writeFileSync(join(archive, "history.jsonl"), "legacy\n");
  const result = await f.call("update_goal", {status: "complete", completion_summary: "Tests passed."});
  assert.equal(result.isError, false); assert.equal(result.details.subject, "completed");
  assert.equal(f.core.goal, undefined);
  assert.equal(existsSync(join(f.cwd, ".pi/goals/simple-goal/record.json")), false);
  assert.equal(existsSync(join(f.cwd, ".pi/goals/archived/simple-goal")), false);
  assert.equal(readFileSync(join(archive, "history.jsonl"), "utf8"), "legacy\n");
  assert.doesNotMatch(result.content[0].text, /archiv/i);
}));
await scenario("Given a current goal When cleared Then end without completion or archive", () => use(async f => {
  await f.command("clear"); assert.equal(f.core.goal, undefined);
  assert.equal(existsSync(join(f.cwd, ".pi/goals/simple-goal/record.json")), false);
  assert.equal(existsSync(join(f.cwd, ".pi/goals/archived")), false);
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
  const text = buildCheckPrompt({objective: "Requirement. ".repeat(500) + "MANDATORY_TAIL", claim: undefined, contract: "Keep correctness."});
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
await scenario("Given checker usage When result returns Then charge the Goal budget", () => use(async f => {
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
await scenario("Given a checker exhausting budget When it returns MET Then stop by budget with one result", () => use(async f=>{
  f.core.store.apply({expectedGoalId:"simple-goal",mutate:d=>({...d,tokenBudget:100})});
  const before=f.sent.length; const r=await f.call("update_goal",{status:"complete"}); assert.equal(r.details.subject,"budget reached");
  assert.equal(f.core.goal?.status,"budget_limited"); assert.equal(f.core.goal?.usage.tokensUsed,1234);
  assert.equal(f.sent.length,before,"the tool owns this budget result, so no duplicate custom message is sent");
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

await scenario("Given pre-creation model usage When a Goal starts Then include it in the budget", () => use(async f=>{
  await f.command("clear"); await f.fire("agent_start");
  await f.fire("message_end",{message:{role:"assistant",usage:{totalTokens:37},content:[{type:"toolCall",name:"create_goal"}]}});
  const r=await f.call("create_goal",{objective:"Run the CSV verification.",token_budget:20});
  assert.equal(f.core.goal?.usage.tokensUsed,37); assert.equal(f.core.goal?.status,"budget_limited"); assert.equal(r.details.subject,"budget reached");
  assert.equal((await f.fire("tool_call",{toolName:"bash"}))?.block,true);
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
    await pending; assert.equal(f.core.store.readGoalFromDisk("simple-goal")?.usage.tokensUsed,80);
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
await scenario("Given stale resume snapshot When budget is exhausted Then refuse resume",()=>use(f=>{
  const old=f.core.goal!;
  f.core.store.apply({expectedGoalId:old.id,mutate:d=>({...d,status:"budget_limited",autoContinue:false,tokenBudget:10,usage:{...d.usage,tokensUsed:10}})});
  assert.equal(f.core.scheduler.resume(old,f.core.settings(f.ctx as never),"user"),false);
  assert.equal(f.core.goal?.autoContinue,false);
}));
await scenario("Given an old-thread checker exceeding cap When cancelled usage returns Then stop its original Goal",async()=>{
  let release!: (value:any)=>void;
  await use(async f=>{
    f.core.store.apply({expectedGoalId:"simple-goal",mutate:d=>({...d,tokenBudget:100})});
    const pending=f.call("update_goal",{status:"complete"});
    f.core.restore({...f.ctx,sessionManager:{getSessionId:()=>"other-thread",getBranch:()=>[]}} as never);
    release({met:false,cancelled:true,report:"Cancelled.",usage:{totalTokens:110}}); await pending;
    const old=f.core.store.readGoalFromDisk("simple-goal")!; assert.equal(old.status,"budget_limited"); assert.equal(old.autoContinue,false);
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
  assert.equal(f.core.store.readGoalFromDisk("simple-goal")?.usage.tokensUsed,55);
}));
await scenario("Given overlapping thread messages When old usage ends after a new run Then keep original attribution",()=>use(async f=>{
  await f.fire("agent_start"); const old={role:"assistant",usage:{totalTokens:55}};
  await f.fire("message_start",{message:old});
  const other={...f.ctx,sessionManager:{getSessionId:()=>"other-thread",getBranch:()=>[]}};
  f.core.restore(other as never); f.core.store.create({id:"other-goal",owner:"other-thread",objective:"Other goal."}); f.core.focus("other-goal",other as never,"created");
  await f.events.get("agent_start")!({},other); await f.fire("message_end",{message:old});
  assert.equal(f.core.store.readGoalFromDisk("simple-goal")?.usage.tokensUsed,55);
  assert.equal(f.core.store.readGoalFromDisk("other-goal")?.usage.tokensUsed,0);
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
console.log(JSON.stringify(results));

if (process.env.PI_E2E_ASSERTION_PATH) writeObservationFile(process.env.PI_E2E_ASSERTION_PATH, JSON.stringify(observedScenarios()));
