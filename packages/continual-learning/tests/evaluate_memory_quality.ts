/** Read-only semantic study; this worker has no Memory/Harness apply API. */
import fs from 'node:fs/promises';
import {createHash} from 'node:crypto';
import {TypeSafeClient, APIError, APITimeoutError, APIUserAbortError} from '@typesafe-ai/sdk';
import {readFrozenResearchManifest} from './frozen-research-manifest';
import {createJevJudge} from '../extensions/jev-learning';
import type {SelectedMemory} from '../extensions/incremental-learning';
import {prepareMemoryQualityCreate, memoryQualityResultingContents, combineMemoryQualityAnswers} from './memory-quality-research';

const [mode, path, expectedHash] = process.argv.slice(2);
if (!['--live','--preflight-only'].includes(mode) || path !== '/home/node/research/manifest.json') throw Error('Explicit research mode and isolated manifest required');
const hash = (bytes: Buffer): string => createHash('sha256').update(bytes).digest('hex');
interface Sample {
  id: string; origin: string; snapshot: unknown; existing: SelectedMemory[]; plan: unknown;
  changes: Parameters<typeof memoryQualityResultingContents>[1];
  expected: {value: boolean[]; omission: boolean}; baseline?: {decision: 'allow' | 'propose'};
}
interface Manifest {
  codeHashes: Record<string,string>; corpus: string; corpusSha256: string;
  paidAllowed: boolean; requestBudget: number; samples: number; model: string;
}
const frozen = await readFrozenResearchManifest<Manifest>(new URL('file://' + path));
const m = frozen.value;
const mandatory = ['/opt/experiment/packages/continual-learning/tests/evaluate_memory_quality.ts',
  '/opt/experiment/packages/continual-learning/tests/memory-quality-research.ts',
  '/opt/experiment/packages/continual-learning/tests/frozen-research-manifest.ts',
  '/home/node/research/cases.json'];
if (frozen.sha256 !== expectedHash || m.model !== 'jev-1.13.0' || m.requestBudget !== 80 || m.samples !== 48
  || m.corpus !== '/home/node/research/cases.json' || mandatory.some(file => !Object.hasOwn(m.codeHashes,file))) throw Error('Invalid frozen research contract');
const bytes = await fs.readFile(m.corpus);
if (hash(bytes) !== m.corpusSha256) throw Error('Corpus changed');
const samples = (JSON.parse(bytes.toString()) as {rows:Sample[]}).rows;
if (samples.length !== m.samples || new Set(samples.map(row => row.id)).size !== m.samples) throw Error('Sample set changed');
const prepared = samples.map(row => {
  const {candidates,questions} = prepareMemoryQualityCreate(row.plan,row.snapshot,row.existing,row.changes);
  if (candidates.length !== row.changes.filter(change => change.op !== 'delete').length
    || row.expected.value.length !== candidates.length) throw Error('Invalid candidate inventory');
  const state = {frozenEvidence:row.snapshot};
  if (Object.keys(questions).length > 32 || Buffer.byteLength(JSON.stringify({state:JSON.stringify(state),questions,model:m.model})) > 64_000) throw Error('Research bounds exceeded');
  return {row,candidates,questions,state};
});
if (mode === '--preflight-only') {
  await fs.writeFile('/home/node/research/preflight.json',JSON.stringify({samples:prepared.length,externalRequests:0,productionWrites:0})+'\n',{flag:'wx',mode:0o600});
} else {
  if (!m.paidAllowed || !process.env.TYPESAFE_API_KEY) throw Error('Paid research denied');
  let qualityRequests = 0;
  const client = new TypeSafeClient({apiKey:process.env.TYPESAFE_API_KEY,defaultModel:m.model,timeout:5000,retry:{maxRetries:0},logLevel:'off',fetch:async(url,init) => {
    qualityRequests++;
    if (qualityRequests > samples.length) throw Error('Quality request budget exceeded');
    return fetch(url,init);
  }});
  const baselineJudge = createJevJudge({enabled:true,apiKey:process.env.TYPESAFE_API_KEY,defaultModel:m.model,
    scopes:['memory'],allowPrivateMemory:true,timeout:5000});
  const rows: Record<string,unknown>[] = [];
  for (const {row,candidates,questions,state} of prepared) {
    await frozen.verify();
    const baseline = row.baseline ?? await baselineJudge.validate('memory',row.snapshot,candidates,row.existing);
    const started = Date.now();
    let quality: Record<string,unknown>;
    try {
      const response = await client.systemOne({model:m.model,state:JSON.stringify(state),questions});
      const usage = response.usage;
      const validUsage = Number.isSafeInteger(usage.input_tokens) && usage.input_tokens >= 0
        && Number.isSafeInteger(usage.output_tokens) && usage.output_tokens >= 0;
      const combined = combineMemoryQualityAnswers(response.answers,candidates.length);
      quality = response.model === m.model && validUsage ? {...combined,answers:response.answers,
        model:response.model,inputTokens:usage.input_tokens,outputTokens:usage.output_tokens,
        estimatedCostUsd:usage.input_tokens*.042/1_000_000} : {decision:'propose',failures:[{reason:'invalid-response'}]};
    } catch (error) {
      quality = {decision:'propose',failures:[{reason:error instanceof APITimeoutError ? 'timeout'
        : error instanceof APIUserAbortError ? 'cancelled' : 'unavailable'}],
        ...(error instanceof APIError && Number.isSafeInteger(error.status) && error.status >= 400 && error.status <= 599 ? {httpStatus:error.status} : {})};
    }
    rows.push({id:row.id,origin:row.origin,expected:row.expected,baseline,
      quality:{...quality,durationMs:Date.now()-started},combinedDecision:baseline.decision === 'allow' && quality.decision === 'allow' ? 'allow' : 'propose'});
    await fs.writeFile('/home/node/research/checkpoint.tmp',JSON.stringify({qualityRequests,rows})+'\n',{mode:0o600});
    await fs.rename('/home/node/research/checkpoint.tmp','/home/node/research/checkpoint.json');
  }
  await frozen.verify();
  await fs.writeFile('/home/node/research/result.json',JSON.stringify({evidence:'real-jev-separate-quality-semantic-study',
    manifestSha256:frozen.sha256,qualityRequests,rows,productionWrites:0,adopted:false,
    limits:['Authored development labels, not human gold or heldout.','Known baseline results are preserved observations, not concurrent reruns.','Fresh baselines have no full parent apply or real storage authorization.','Quality allow never grants write permission.','No Pi candidate generation, actual Memory writes, recall or Harness effects in this semantic study.']})+'\n',{flag:'wx',mode:0o600});
}
console.log(JSON.stringify({mode,samples:samples.length,completed:true,productionWrites:0}));
