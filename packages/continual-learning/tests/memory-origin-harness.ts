import fs from "node:fs/promises";
import path from "node:path";
import {spawnSync} from "node:child_process";
import {createConsolidationRun, releaseConsolidationRun, createPreApplyReceipt, createConsolidationReceipt, writeConsolidationReceipt, sha256Digest, hashMemoryRoot, writeFileAtomic, acquireConsolidationLock, resolveConsolidationRunPaths} from "../extensions/consolidation-run";
import {recordLearningMutation, recordLearningProposal, listLearningHistory, previewLearningUndo, undoLearningChange, readMemoryOriginContext} from "../extensions/learning-history";

const root = process.env.PROBE_DIR!;
export async function fixture(label: string, count = 3, classification = "private", git = false, legacy = false,
  options: {cwd?: string; name?: string; content?: string; purpose?: string; sourceText?: string} = {}) {
  const name = options.name ?? "contract.md";
  const cwd = options.cwd ?? path.join(root, label); await fs.mkdir(cwd, {recursive: true});
  if (git && spawnSync("git", ["init", "-q"], {cwd}).status !== 0) throw new Error("Fixture Git init failed");
  const records: Array<{id: string; file: string; runDir: string; snapshot: unknown}> = [];
  const memory = resolveConsolidationRunPaths(cwd).memory;
  const target = path.join(memory.harnessDir, name);
  async function apply(index: number, create = index === 0) {
    const purpose = options.purpose ?? (index === 0 ? "Remember the currently observed contract for future maintenance." : `Maintain the observed contract ${index}.`);
    const sourceText = options.sourceText ?? `Source V${index}.`;
    const entries = [{role:"user",content:[{type:"text",text:purpose}],metadata:{complete:true}},
      {role:"assistant",content:[{type:"toolCall",id:"read",name:"read",arguments:{path:path.join(cwd,"source.ts")}}]},
      {role:"toolResult",toolCallId:"read",toolName:"read",isError:false,content:[{type:"text",text:sourceText},{type:"text",text:"Complete trailing context."}]}];
    const run = await createConsolidationRun({cwd,sessionManager:{getBranch:()=>entries}},cwd,false);
    const m=run.manifest, content=options.content ?? `---\nname: contract\ndescription: Source V${index}.\ntype: project\n---\nSource V${index}.\n`;
    const candidate={name,kind:create?"project":"rewrite",classification,content,evidence:[{index:2,quote:sourceText,role:"toolResult"}]};
    const plan={kind:"memory-consolidation-plan",version:1,schemaVersion:1,runId:m.runId,scopeKey:m.scopeKey,scopeDigest:m.scopeDigest,artifactHash:m.snapshotDigest,snapshotDigest:m.snapshotDigest,
      selected:create?[]:[name],operations:create?[]:[candidate],newMemories:create?[candidate]:[]};
    const text=JSON.stringify(plan,null,2)+"\n",planDigest=sha256Digest(text);
    try {
      await fs.writeFile(run.paths.planFile,text);
      await writeConsolidationReceipt(run,createPreApplyReceipt({runId:m.runId,scopeDigest:m.scopeDigest,artifactHash:m.snapshotDigest,selected:plan.selected,sourceHashes:m.sourceHashes,planDigest}),"pre");
      await fs.mkdir(memory.harnessDir,{recursive:true});
      const shared=memory.publicDir?path.join(memory.publicDir,name):undefined;
      await recordLearningMutation(cwd,"memory",[target,...(shared?[shared]:[])],async()=>{
        await writeFileAtomic(target,content,0o600);
        if(shared && classification==="safe"){await fs.mkdir(memory.publicDir!,{recursive:true});await writeFileAtomic(shared,content,0o644)}
        await writeConsolidationReceipt(run,createConsolidationReceipt(m,plan.selected,{harness:await hashMemoryRoot(m.harnessDir),public:memory.publicDir?await hashMemoryRoot(memory.publicDir):{}},planDigest,create?[name]:[]));
        return {outcome:"applied"};
      },plan,legacy&&index===0?undefined:{run,planPath:run.paths.planFile,planDigest});
      const record=(await listLearningHistory(cwd)).find(r=>r.changes.some(c=>c.target.root==="private"&&c.target.name===name&&c.after?.digest===sha256Digest(content)))!;
      records.push({id:record.id,file:path.join(memory.agentDir,"memory/history",memory.scopeKey,record.id+".json"),runDir:run.paths.runDir,snapshot:JSON.parse(await fs.readFile(run.paths.snapshotFile,"utf8"))});
    } finally {await releaseConsolidationRun(run,{keepArtifacts:true})}
  }
  for(let i=0;i<count;i++)await apply(i);
  const load=async(options={})=>{
    const lock=await acquireConsolidationLock(resolveConsolidationRunPaths(cwd));
    try{return await readMemoryOriginContext(cwd,name,options)}finally{await lock.release()}
  };
  return {cwd,memory,target,records,apply,load};
}

async function main(mode: string) {
  const f=await fixture(mode,mode==="creation"?1:3,mode.startsWith("safe")?"safe":"private",mode==="safe-git",mode==="legacy");
  const edit=async(index:number,change:(value:any)=>void)=>{const p=f.records[index].file,v=JSON.parse(await fs.readFile(p,"utf8"));change(v);await fs.writeFile(p,JSON.stringify(v));};
  if(mode==="beyond-display")for(let i=0;i<55;i++)await recordLearningProposal(f.cwd,"memory",{unrelated:i});
  if(mode==="manual-current"){const body=await fs.readFile(f.target);await fs.writeFile(f.target,"Manual change.");await writeFileAtomic(f.target,body,0o600)}
  if(mode==="manual-chain"){const body=await fs.readFile(f.target);await fs.writeFile(f.target,"Manual change.");await writeFileAtomic(f.target,body,0o600);await f.apply(3)}
  if(mode==="undone"){const last=f.records.at(-1)!;const p=await previewLearningUndo(f.cwd,last.id);await undoLearningChange(f.cwd,last.id,p.digest)}
  if(mode==="pending")await edit(2,v=>v.status="pending");
  if(mode==="duplicate"){
    const v=JSON.parse(await fs.readFile(f.records[2].file,"utf8"));v.id="change_duplicate_1234567890abcdef";v.createdAt="1900-01-01";
    await fs.writeFile(path.join(path.dirname(f.records[2].file),v.id+".json"),JSON.stringify(v));
  }
  if(mode==="case-alias")await edit(0,v=>v.changes[0].target.name="CONTRACT.md");
  if(mode==="artifact")await fs.appendFile(path.join(f.records[0].runDir,"snapshot.json")," ");
  if(mode==="wrong-created"){
    const p=path.join(f.records[0].runDir,"post-receipt.json"),v=JSON.parse(await fs.readFile(p,"utf8"));v.created=[];await fs.writeFile(p,JSON.stringify(v));
    await edit(0,r=>r.origin.artifactHashes["post-receipt.json"]=sha256Digest(JSON.stringify(v)));
  }
  if(mode==="foreign"){
    const p=path.join(f.records[0].runDir,"manifest.json"),v=JSON.parse(await fs.readFile(p,"utf8"));v.cwd=path.join(f.cwd,"foreign");await fs.writeFile(p,JSON.stringify(v));
    await edit(0,r=>r.origin.artifactHashes["manifest.json"]=sha256Digest(JSON.stringify(v)));
  }
  if(mode==="new-incarnation"){await fs.unlink(f.target);await f.apply(3,true)}
  if(mode==="unrelated-undone"){
    const file=path.join(f.memory.harnessDir,"other.md");await recordLearningMutation(f.cwd,"memory",[file],()=>fs.writeFile(file,"Other knowledge."));
    const other=(await listLearningHistory(f.cwd)).find(r=>r.changes.some(c=>c.target.name==="other.md"))!;other.status="undone";
    await fs.writeFile(path.join(path.dirname(f.records[0].file),other.id+".json"),JSON.stringify(other));
  }
  const limits=mode.startsWith("bound-")?{[mode.slice(6)]:1}:undefined;
  const before=await fs.readFile(f.target).catch(()=>Buffer.from(""));
  const result=await f.load(limits?{limits}:{});
  let changedRejected=false,contextEditRejected=false;
  if(result.status==="available"){
    if(mode==="race-record")await edit(1,v=>v.status="undone");
    if(mode==="race-inventory"){
      const p=f.records[0].file,v=JSON.parse(await fs.readFile(p,"utf8"));v.id="change_new_1234567890abcdef";
      await fs.writeFile(path.join(path.dirname(p),v.id+".json"),JSON.stringify(v));
    }
    if(mode.startsWith("race-")){try{await result.assertUnchanged()}catch{changedRejected=true}}
    else {
      await result.assertUnchanged();
      if(mode==="context-edit"){result.context.transactions[0].snapshot.extra="Changed by caller";try{await result.assertUnchanged()}catch{contextEditRejected=true}}
    }
  }
  console.log(JSON.stringify({mode,result,changedRejected,contextEditRejected,currentUnchanged:before.equals(await fs.readFile(f.target)),expectedSnapshot:f.records[mode==="new-incarnation"?3:0].snapshot,paidRequests:0}));
}
if(import.meta.main)await main(process.argv[2]);
