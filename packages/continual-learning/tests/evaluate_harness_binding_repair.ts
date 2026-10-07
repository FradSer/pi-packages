/** Native generator output validation; this research has no apply path. */
import fs from 'node:fs/promises';
import {createHash} from 'node:crypto';
import path from 'node:path';
import {parsePiWorkerOutput} from '@fradser/pi-kit';
import {validateHarnessPlan,learnedRuleRevisionsFromConfig,type HarnessConsolidationPlan} from '../extensions/harness-consolidation';
import {loadLayers} from '../extensions/guardrail-config';
import {DEFAULT_RULES} from '../extensions/guardrail-engine';
import {createJevJudge,type BoundScopeContext} from '../extensions/jev-learning';
import {addHarnessRepairBindings,checkFrozenHarnessRepair,BINDING_INSTRUCTIONS} from './harness-binding-repair-research';
const hash=(v:Buffer|string)=>createHash('sha256').update(v).digest('hex');
const mode=process.argv[2];if(!['--preflight-only','--live'].includes(mode))throw Error('Explicit research mode required');
const inputPath=process.argv[3];
interface Input {paidAllowed:boolean;files:Record<string,string>;runDirectory:string;beforeTask:string;afterTask:string;stdout?:string;output:string;projectRoot:string;projectRecords:Record<string,{type:string;mode:number;sha256?:string}>}
const input:Input=JSON.parse(await fs.readFile(inputPath,'utf8'));
async function verify(){
 for(const [p,h]of Object.entries(input.files))if(hash(await fs.readFile(p))!==h)throw Error('Frozen original input changed');
 const found=new Set<string>();
 async function visit(relative:string){
  const entry=input.projectRecords[relative],target=path.join(input.projectRoot,relative),stat=await fs.lstat(target);
  if(!entry||stat.isSymbolicLink()||(stat.mode&0o777)!==entry.mode||(stat.isDirectory()?'directory':'file')!==entry.type)throw Error('Frozen project path or permissions changed');
  found.add(relative);
  if(stat.isDirectory())for(const name of await fs.readdir(target))await visit(relative==='.'?name:path.join(relative,name));
  else if(hash(await fs.readFile(target))!==entry.sha256)throw Error('Frozen project content changed');
 }
 await visit('.');
 if(found.size!==Object.keys(input.projectRecords).length)throw Error('Frozen project entry missing');
}
await verify();
if(mode==='--live'&&(!input.paidAllowed||!process.env.TYPESAFE_API_KEY))throw Error('Paid research guard denied');
const before=await fs.readFile(input.beforeTask,'utf8'),after=await fs.readFile(input.afterTask,'utf8');
if(addHarnessRepairBindings(before)!==after)throw Error('Prepared prompt differs from exact production additions');
const source=await fs.readFile(new URL('../extensions/harness-consolidation.ts',import.meta.url),'utf8');
if(!BINDING_INSTRUCTIONS.every(s=>source.includes(s)))throw Error('Production guidance changed');
const payload=JSON.parse(before.split('\n').at(-1)!);
const original:HarnessConsolidationPlan=payload.rejectedPlan;
const manifest=JSON.parse(await fs.readFile(input.runDirectory+'/manifest.json','utf8'));
const snapshotText=await fs.readFile(input.runDirectory+'/snapshot.json','utf8'),snapshot:unknown=JSON.parse(snapshotText);
if(hash(snapshotText)!==manifest.snapshotDigest||original.runId!==manifest.runId||original.scopeDigest!==manifest.scopeDigest||original.artifactHash!==manifest.snapshotDigest)throw Error('Original parent identity mismatch');
let local:unknown;try{local=JSON.parse(await fs.readFile(manifest.cwd+'/.pi/harness.json','utf8'));}catch(error){if((error as NodeJS.ErrnoException).code!=='ENOENT')throw Error('Original project configuration unreadable');local=undefined;}
const options={snapshot,snapshotText,availableSkills:[],automatic:true,targetSource:'project' as const,layers:[{source:'built-in defaults',rules:DEFAULT_RULES.map(rule=>({...rule}))},...loadLayers(manifest.cwd)],learnedRules:learnedRuleRevisionsFromConfig(local)};
if(validateHarnessPlan(original,options).length)throw Error('Original plan not parent valid');
if(mode==='--preflight-only'){
 await fs.writeFile(input.output,JSON.stringify({evidence:'offline-original-input-preflight',parentValid:true,exactPromptTransform:true,externalRequests:0,productionWrites:0})+'\n');
}else{
 if(!input.stdout)throw Error('Native generator output missing');
 const stdout=await fs.readFile(input.stdout,'utf8'),checked=checkFrozenHarnessRepair(stdout,original,options);
 const worker=parsePiWorkerOutput(stdout);
 let verdict:unknown;
 if(checked.category==='ready'){
  const parentScope:BoundScopeContext=Object.freeze({repoRoot:manifest.cwd,runId:manifest.runId,scopeKey:manifest.scopeKey,evidenceDigest:hash(JSON.stringify(snapshot))});
  verdict=await createJevJudge({enabled:true,apiKey:process.env.TYPESAFE_API_KEY,defaultModel:'jev-1.13.0',scopes:['harness'],allowPrivateMemory:true,timeout:5000}).validate('harness',snapshot,checked.plan.operations as unknown[],[],undefined,checked.plan.evidence,parentScope);
 }
 await verify();
 await fs.writeFile(input.output,JSON.stringify({evidence:'real-native-repair-generation-and-jev-on-frozen-original',nativeOutputSha256:hash(stdout),parentCategory:checked.category,mainUsage:worker.usage,verdict,productionWrites:0,limits:['One known original input; not heldout or full-workflow quality.','Retention comparison follows existing contract independently; no parent mutation queue or apply invoked.']})+'\n');
}
console.log(JSON.stringify({mode,completed:true,productionWrites:0}));
