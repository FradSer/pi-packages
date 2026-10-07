import fs from "node:fs";
import path from "node:path";
import { executeIntentTool } from "../../src/intent-tools.ts";
import { spawnResident, terminateAllAgents } from "../../src/spawner.ts";
import { listAgents } from "../../src/roster.ts";
import type { SessionNotice } from "../../src/session-result.ts";

const root = "/results";
const model = "cli-proxy/opencode/deepseek-v4.1-flash";
const notices: SessionNotice[] = [];
const waiters = new Map<string, (notice: SessionNotice) => void>();
const receipts: unknown[] = [];
const spawns: unknown[] = [];
const audit = path.resolve("/opt/study/packages/subagents/tests/docker-study/audit.ts");
const delivery = (notice: SessionNotice) => {
  notices.push(notice);
  fs.appendFileSync(`${root}/notices.jsonl`,JSON.stringify(notice)+"\n");
  if ("inputId" in notice && notice.inputId) waiters.get(notice.inputId)?.(notice);
};
function options(parent: string) {
  return {cwd:"/work",parentSessionId:parent,leaderModel:()=>model,thinking:()=>"off",deliverSessionResult:delivery,
    spawn: (input: Parameters<typeof spawnResident>[0]) => {
      const result=spawnResident({...input,extensions:[...(input.extensions??[]),audit]});
      spawns.push({name:input.agentName,session:input.session,sessionDir:input.sessionDir,tools:input.tools,result});
      fs.writeFileSync(`${root}/spawns.json`,JSON.stringify(spawns,null,2)); return result;
    }};
}
async function tool(name: Parameters<typeof executeIntentTool>[0], params: unknown, parent: string) {
  const result=await executeIntentTool(name,params,options(parent));
  receipts.push({name,params,data:result.structuredContent,error:result.isError});
  fs.writeFileSync(`${root}/receipts.json`,JSON.stringify(receipts,null,2));
  return result.structuredContent;
}
async function settled(inputId: string): Promise<SessionNotice> {
  const existing=notices.find(n=>"inputId" in n&&n.inputId===inputId); if(existing)return existing;
  return await new Promise((resolve,reject)=> {const timer=setTimeout(()=>{waiters.delete(inputId);reject(new Error(`Result deadline ${inputId}`));},180000);
    waiters.set(inputId,n=>{clearTimeout(timer);waiters.delete(inputId);resolve(n);});});
}
function definition(name:string,tools:string[]) {
  const dir=`/agent/agents/${name}`;fs.mkdirSync(dir,{recursive:true});
  fs.writeFileSync(`${dir}/agent.md`,`---\nname: ${name}\ndescription: Review Pi package contracts and report evidence.\ntools: ${tools.join(", ")}\n---\nReview supplied source only. Report confirmed bugs with concrete evidence. Read relevant capability entries when the Memory index is useful. Do not treat proposals as accepted Memory.\n`);
}
async function run(params:Record<string,unknown>,parent:string) {
  const data=await tool("agent_start",params,parent);
  if(!data.ok||!data.session||!data.inputId) throw new Error(`Start refused: ${JSON.stringify(data)}`);
  const notice=await settled(data.inputId);
  const stop=await tool("agent_stop",{session:data.session},parent);
  return {data,notice,stop};
}
const report:Record<string,unknown>={model,piVersion:JSON.parse(fs.readFileSync("/opt/study/node_modules/@earendil-works/pi-coding-agent/package.json","utf8")).version};
function save(){fs.writeFileSync(`${root}/study.json`,JSON.stringify(report,null,2));}
try {
  const lifecycle=[];
  for (const saved of [false,true]) {
    if(saved)definition("resident",["read","agent_memory"]);
    for(let attempt=0;attempt<3;attempt++) {
      const parent=`lifecycle-${saved}-${attempt}`;
      const data=await tool("agent_start",{...(saved?{identity:"resident"}:{label:"resident"}),tools:[],prompt:"Reply exactly FIRST_OK."},parent);
      if(!data.ok||!data.session||!data.inputId)throw new Error(JSON.stringify(data));
      const first=await settled(data.inputId);
      const next=await tool("agent_input",{session:data.session,prompt:"Reply exactly SECOND_OK.",delivery:"next"},parent);
      if(!next.inputId)throw new Error(JSON.stringify(next));
      const second=await settled(next.inputId);
      const idle=listAgents().find(a=>a.spawnId===data.session!.split(":").at(-1))?.status;
      const stop=await tool("agent_stop",{session:data.session},parent);
      const stale=await tool("agent_input",{session:data.session,prompt:"MUST_NOT_RUN",delivery:"next"},parent);
      lifecycle.push({saved,attempt,data,first,second,idle,stop,stale});report.lifecycle=lifecycle;save();
    }
  }
  report.restart=await run({identity:"resident",tools:[],prompt:"What exact reply did you give to the last input in this conversation before this one? Return only that reply, or UNKNOWN if no prior conversation."},"lifecycle-true-0");save();
  const queuedStart=await tool("agent_start",{label:"queued",tools:[],prompt:"Reply exactly QUEUED_FIRST."},"queued");
  if(!queuedStart.session||!queuedStart.inputId)throw new Error(JSON.stringify(queuedStart));
  const queuedNext=await tool("agent_input",{session:queuedStart.session,prompt:"Reply exactly QUEUED_SECOND.",delivery:"next"},"queued");
  if(!queuedNext.inputId)throw new Error(JSON.stringify(queuedNext));
  report.queued={start:queuedStart,next:queuedNext,first:await settled(queuedStart.inputId),second:await settled(queuedNext.inputId),stop:await tool("agent_stop",{session:queuedStart.session},"queued")};save();
  report.invalidIdentity=await tool("agent_start",{identity:"not-defined",prompt:"MUST_NOT_RUN"},"invalid");
  report.identityWithInstructions=await tool("agent_start",{identity:"resident",instructions:"override",prompt:"MUST_NOT_RUN"},"invalid");
  definition("readonly-reviewer",["read","agent_memory"]);
  report.readonly=await run({identity:"readonly-reviewer",prompt:'Call agent_memory with action append, name "review-method", description "Review resource packaging", body "When reviewing a Pi package, compare runtime file reads with manifest files. This method does not prove live behavior.". After the refusal, call action propose with the same name, description and body and evidence "training fixture only". Report the two outcomes.'},"readonly-training");save();
  definition("learned-reviewer",["read","write","agent_memory"]);
  fs.mkdirSync("/work/training",{recursive:true});
  fs.writeFileSync("/work/training/examples.md",`Three verified review examples:\n1. An async result callback invokes sendMessage returning a promise without returning or awaiting it. Rejections escape the execution boundary. Await or return the promise and retain attribution on failure. A synchronous callback is not evidence delivery completed.\n2. A stop request deletes a child's ownership record before native closure confirmation. Late frames can be attributed to a successor. Record stopping intent; retain exact incarnation ownership until closure confirms.\n3. A Pi extension reads prompts/reviewer.md via import.meta.url, but package.json files includes only index.ts and src. Installed consumers cannot read that prompt. Check every runtime resource against packed manifest; local source execution does not prove packaging.\nThese are general review methods, not claims that any current repository has these bugs.\n`);
  report.training=await run({identity:"learned-reviewer",prompt:'Read /work/training/examples.md. Synthesize one reusable review capability for promise delivery, exact process closure, and packed runtime resources. Use agent_memory action append with name "pi-review-boundaries", a one-line applicability description, and body containing checks, evidence requirements and limits. Do not copy project paths or claim untested bugs. Then report what you recorded.'},"training");save();
  const memoryDir="/agent/agents/learned-reviewer/memory";
  report.memoryFiles=fs.existsSync(memoryDir)?fs.readdirSync(memoryDir).filter(f=>f.endsWith(".md")).map(f=>({file:f,body:fs.readFileSync(`${memoryDir}/${f}`,"utf8")})):[];save();
  const cases=[
    {name:"delivery",expected:"unhandled-delivery",source:'export function deliver(send: (text:string)=>Promise<void>, text:string): void { send(text); }',contract:'The caller must observe asynchronous delivery failures; no fire-and-forget delivery is allowed.'},
    {name:"closure",expected:"premature-release",source:'export async function close(registry: Map<string,unknown>, name:string, stop:()=>Promise<boolean>) { registry.delete(name); const confirmed=await stop(); return confirmed; }',contract:'Ownership remains reserved until stop positively confirms native process closure.'},
    {name:"packaging",expected:"missing-resource",source:'import fs from "node:fs"; export function prompt(){return fs.readFileSync(new URL("../prompts/review.md",import.meta.url),"utf8");}',contract:'The extension must function after npm pack/install, with runtime resources bundled.'},
    {name:"safe",expected:null,source:'export async function deliver(send:(text:string)=>Promise<void>, text:string){await send(text);} export async function close(registry:Map<string,unknown>,name:string,stop:()=>Promise<boolean>){const confirmed=await stop();if(confirmed)registry.delete(name);return confirmed;}',contract:'Delivery errors propagate. Ownership is released only on confirmed closure. No other requirements.'},
  ];
  const evaluations=[];
  for(const c of cases) {
    const dir=`/work/heldout/${c.name}`;fs.mkdirSync(dir,{recursive:true});fs.writeFileSync(`${dir}/index.ts`,c.source);
    fs.writeFileSync(`${dir}/README.md`,c.contract);
    fs.writeFileSync(`${dir}/package.json`,JSON.stringify({type:"module",files:["index.ts"],name:`fixture-${c.name}`}));
    fs.mkdirSync(`${dir}/prompts`,{recursive:true});fs.writeFileSync(`${dir}/prompts/review.md`,"Review source.");
    const prompt=`Review only ${dir}. Read README.md, index.ts and package.json. Return a JSON object with findings (array of {code,evidence,consequence}) and limitations. Valid codes: unhandled-delivery, premature-release, missing-resource. Use these codes only for confirmed applicable defects. Do not flag unrelated issues; return an empty findings array for correct code. Do not change files or write Memory. Use relevant accepted capabilities if available.`;
    for(const withMemory of [false,true]) {
      const hidden=`/results/accepted-memory-hidden-${c.name}`;
      if(!withMemory)fs.renameSync(memoryDir,hidden);
      let result;
      try {
        result=await run({identity:"learned-reviewer",tools:["read"],prompt},`heldout-${c.name}-${withMemory}`);
      } finally {
        if(!withMemory) {
          if(fs.existsSync(memoryDir))fs.renameSync(memoryDir,`/results/empty-memory-${c.name}`);
          fs.renameSync(hidden,memoryDir);
        }
      }
      evaluations.push({case:c.name,expected:c.expected,withMemory,...result});report.evaluations=evaluations;save();
    }
  }
  report.finalRoster=listAgents().map(a=>({name:a.name,status:a.status}));report.completed=true;save();
} catch(error){report.error=error instanceof Error?error.stack:String(error);save();process.exitCode=1;}
finally {report.closure=await terminateAllAgents();save();}
