/** Explicit isolated native generation + Jev research; never an apply path. */
import fs from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {modelRef} from '@fradser/pi-kit';
import {createHash} from 'node:crypto';
import {repairIncrementalMemoryPlan} from '../extensions/inject-memory';
import {createJevJudge} from '../extensions/jev-learning';
import {checkDurableCoreRepair,DURABLE_CORE_CLARIFICATION,validDurableCoreFreezeSet,type DurableCoreCase} from './durable-core-generator-research';
const hash = (bytes: Buffer | string): string => createHash('sha256').update(bytes).digest('hex');
interface Input {
  paidAllowed: boolean; caseId: string; arm: 'before' | 'after';
  cases: string; hashes: Record<string, string>;
  model: {provider: string; model: string};
}
const mode = process.argv[2], inputPath = process.argv[3], expectedHash = process.argv[4];
if (!['--preflight-only','--live'].includes(mode) || !inputPath || !expectedHash) throw Error('Explicit frozen research input required');
const bytes = await fs.readFile(inputPath);
if (hash(bytes) !== expectedHash) throw Error('Research input changed');
const input: Input = JSON.parse(bytes.toString('utf8'));
const directory = '/home/node/research';
if (path.dirname(inputPath) !== directory || !['before','after'].includes(input.arm)) throw Error('Research scope invalid');
async function runtimeFiles(directory: string): Promise<string[]> {
  const files: string[] = [];
  for (const entry of await fs.readdir(directory,{withFileTypes:true})) {
    const file = path.join(directory,entry.name);
    if (entry.isSymbolicLink()) throw Error('Unexpected runtime alias');
    if (entry.isDirectory()) files.push(...await runtimeFiles(file));
    else if (entry.isFile()) files.push(file);
  }
  return files;
}
if (input.cases !== directory + '/cases.json') throw Error('Unexpected corpus path');
const sdk = fileURLToPath(import.meta.resolve('@typesafe-ai/sdk'));
const required = [input.cases,fileURLToPath(import.meta.url),
  fileURLToPath(new URL('./durable-core-generator-research.ts',import.meta.url)),
  '/opt/experiment/packages/kit/index.ts','/opt/experiment/packages/kit/package.json',
  '/opt/experiment/packages/continual-learning/index.ts','/opt/experiment/packages/continual-learning/package.json',
  ...await runtimeFiles('/opt/experiment/packages/kit/src'),
  ...await runtimeFiles('/opt/experiment/packages/continual-learning/extensions'),
  ...await runtimeFiles('/opt/experiment/packages/continual-learning/prompts'),
  ...await runtimeFiles(path.dirname(sdk)),path.join(path.dirname(sdk),'../package.json')];
// The SDK package parent is canonicalized to avoid allowing dot segments.
required[required.length - 1] = path.resolve(required[required.length - 1]);
if (!validDurableCoreFreezeSet(input.hashes,required)) throw Error('Required frozen sources missing');
async function verify(): Promise<void> {
  if (hash(await fs.readFile(inputPath)) !== expectedHash) throw Error('Research input changed');
  for (const [file, digest] of Object.entries(input.hashes)) {
    if (hash(await fs.readFile(file)) !== digest) throw Error('Frozen research source changed');
  }
}
await verify();
const dataset: {cases: DurableCoreCase[]} = JSON.parse(await fs.readFile(input.cases,'utf8'));
const item = dataset.cases.find(candidate => candidate.id === input.caseId);
if (!item || checkDurableCoreRepair(item.rejectedPlan,item).category !== 'ready') throw Error('Frozen case is not eligible');
const errors = [...item.errors, ...(input.arm === 'after' ? [DURABLE_CORE_CLARIFICATION] : [])];
if (errors.length > 16 || errors.some(error => error.length > 800)) throw Error('Repair guidance would be truncated');
if (mode === '--preflight-only') {
  await fs.writeFile(directory + '/preflight.json', JSON.stringify({caseId:item.id,arm:input.arm,parentQuoteChecks:true,externalRequests:0,productionWrites:0}) + '\n',{flag:'wx',mode:0o600});
} else {
  if (input.paidAllowed !== true || !process.env.TYPESAFE_API_KEY || process.env.PI_CODING_AGENT_DIR !== '/home/node/agent') throw Error('Paid research denied');
  const selected = JSON.parse(await fs.readFile('/home/node/agent/memory.json','utf8'));
  if (selected.provider !== input.model.provider || selected.model !== input.model.model) throw Error('Main model changed');
  // One main repair invocation and at most the normal two small-evidence Jev
  // requests; the host transport also enforces the frozen per-arm request cap.
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 300_000);
  let generated: Awaited<ReturnType<typeof repairIncrementalMemoryPlan>>;
  try {
    generated = await repairIncrementalMemoryPlan({identity:item.identity,rejectedPlan:item.rejectedPlan,
      errors,selectedNames:[],semanticContext:{frozenEvidence:item.snapshot,existingMemories:item.existingMemories},
      model:modelRef(input.model),signal:controller.signal});
  } finally {clearTimeout(timer);}
  await verify();
  const checked = generated.plan ? checkDurableCoreRepair(generated.plan,item) : {category:'missing' as const};
  let verdict: Awaited<ReturnType<ReturnType<typeof createJevJudge>['validate']>> | undefined;
  if (checked.category === 'ready') {
    verdict = await createJevJudge({enabled:true,apiKey:process.env.TYPESAFE_API_KEY,scopes:['memory'],
      defaultModel:'jev-1.13.0',timeout:5000,allowPrivateMemory:true})
      .validate('memory',item.snapshot,checked.candidates,item.existingMemories);
  }
  await verify();
  await fs.writeFile(directory + '/result.json',JSON.stringify({evidence:'real-native-repair-and-jev-on-synthetic-fixed-case',
    caseId:item.id,scenario:item.scenario,language:item.language,arm:input.arm,
    generated:{outcome:generated.outcome,durationMs:generated.durationMs,usage:generated.usage,plan:generated.plan},
    parentCategory:checked.category,verdict,productionWrites:0,
    limits:['Synthetic prospective development, not heldout or human gold.','Fixed errors are authored repair scenarios, not observed original Jev rejection.','Structure-valid output is not full apply validation or write authority.','Independent knowledge-preservation review still required.']})+'\n',{flag:'wx',mode:0o600});
}
console.log(JSON.stringify({mode,caseId:item.id,arm:input.arm,completed:true,productionWrites:0}));
