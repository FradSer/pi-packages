/** Explicit, read-only research: no generation, Memory apply or Harness APIs. */
import fs from 'node:fs/promises';
import {createHash} from 'node:crypto';
import {TypeSafeClient, APIError, APITimeoutError, APIUserAbortError, type Questions, type SystemOneResult} from '@typesafe-ai/sdk';
import {containsSensitiveMemoryMaterial} from '../extensions/consolidation-run';
import {readFrozenResearchManifest} from './frozen-research-manifest';
import {prepareMemoryQualityCreate,memoryQualityResultingContents,memoryQualityQuestions} from './memory-quality-research';
import {requestCompletenessQuestions,combineRequestCompletenessAnswers,type FrozenRequirement} from './request-completeness-research';

const [mode,path,expectedHash] = process.argv.slice(2);
if (!['--live','--preflight-only'].includes(mode) || path !== '/home/node/research/manifest.json') throw Error('Isolated explicit research required');
interface Sample {
  id: string; origin: string; scenario: string; language: string; snapshot: unknown; plan: unknown;
  existing: Parameters<typeof memoryQualityResultingContents>[0]; changes: Parameters<typeof memoryQualityResultingContents>[1];
  requirements: FrozenRequirement[]; expectedPreserved: boolean[]; expected: {omission: boolean};
}
interface Manifest {codeHashes: Record<string,string>; paidAllowed: boolean; requestBudget: number; samples: number; corpus: string; corpusSha256: string; model: string}
const frozen = await readFrozenResearchManifest<Manifest>(new URL('file://' + path)), m = frozen.value;
const hash = (bytes: Buffer): string => createHash('sha256').update(bytes).digest('hex');
const required = ['evaluate_request_completeness.ts','request-completeness-research.ts','memory-quality-research.ts','frozen-research-manifest.ts'];
if (frozen.sha256 !== expectedHash || m.samples !== 20 || m.requestBudget !== 20 || m.model !== 'jev-1.13.0'
  || m.corpus !== '/home/node/research/cases.json'
  || required.some(name => !Object.hasOwn(m.codeHashes,'/opt/experiment/packages/continual-learning/tests/'+name))) throw Error('Frozen research contract invalid');
const bytes = await fs.readFile(m.corpus);
if (hash(bytes) !== m.corpusSha256) throw Error('Corpus changed');
const rows = (JSON.parse(bytes.toString()) as {rows:Sample[]}).rows;
if (rows.length !== m.samples || new Set(rows.map(row => row.id)).size !== m.samples) throw Error('Sample set changed');
const prepared = rows.map(row => {
  prepareMemoryQualityCreate(row.plan,row.snapshot,row.existing,row.changes);
  const contents = memoryQualityResultingContents(row.existing,row.changes)
    .map(body => body.replace(/^---\r?\n[\s\S]*?\r?\n---(?:\r?\n|$)/,''));
  const questions = {whole_omission:memoryQualityQuestions([],contents).omission,
    ...requestCompletenessQuestions(row.snapshot,row.requirements,contents)};
  if (row.requirements.length !== row.expectedPreserved.length || row.expectedPreserved.some(value => typeof value !== 'boolean')
    || row.expected.omission !== !row.expectedPreserved.every(Boolean)) throw Error('Evaluation labels invalid');
  const state = {frozenEvidence:row.snapshot};
  const wire = JSON.stringify({model:m.model,state:JSON.stringify(state),questions});
  if (Object.keys(questions).length > 32 || Buffer.byteLength(wire) > 64_000 || containsSensitiveMemoryMaterial(wire)) throw Error('Research privacy or size bounds');
  return {row,state,questions};
});
if (mode === '--preflight-only') {
  await fs.writeFile('/home/node/research/preflight.json',JSON.stringify({samples:prepared.length,judgments:prepared.reduce((sum,r) => sum+Object.keys(r.questions).length,0),externalRequests:0,productionWrites:0})+'\n',{flag:'wx',mode:0o600});
} else {
  if (!m.paidAllowed || !process.env.TYPESAFE_API_KEY) throw Error('Paid research denied');
  let requests = 0;
  const client = new TypeSafeClient({apiKey:process.env.TYPESAFE_API_KEY,defaultModel:m.model,timeout:5000,retry:{maxRetries:0},logLevel:'off',fetch:async(url,init) => {
    if (++requests > m.requestBudget) throw Error('Request budget exceeded');
    return fetch(url,init);
  }});
  const results: Record<string,unknown>[] = [];
  for (const {row,state,questions} of prepared) {
    await frozen.verify(); const start = Date.now(); let result: Record<string,unknown>;
    try {
      const response: SystemOneResult<Questions> = await client.systemOne({model:m.model,state:JSON.stringify(state),questions});
      const validUsage = Number.isSafeInteger(response.usage.input_tokens) && response.usage.input_tokens >= 0
        && Number.isSafeInteger(response.usage.output_tokens) && response.usage.output_tokens >= 0;
      const answer = response.answers.whole_omission;
      if (response.model !== m.model || !validUsage || Object.keys(response.answers).length !== Object.keys(questions).length
        || Object.keys(questions).some(key => !Object.hasOwn(response.answers,key)) || answer?.type !== 'noul'
        || !Number.isFinite(answer.noul) || answer.noul < 0 || answer.noul > 1) throw Error('Invalid research response');
      const answers = Object.fromEntries(Object.entries(response.answers).filter(([key]) => key !== 'whole_omission'));
      const perRequirement = combineRequestCompletenessAnswers(answers,row.requirements.length);
      result = {model:response.model,writeAuthorized:false,whole:{writeAuthorized:false,probability:answer.noul,status:answer.noul <= .1 ? 'complete' : answer.noul >= .9 ? 'incomplete' : 'uncertain'},
        perRequirement,answers:response.answers,inputTokens:response.usage.input_tokens,outputTokens:response.usage.output_tokens,
        estimatedCostUsd:response.usage.input_tokens*.042/1_000_000};
    } catch (error) {
      result = {status:error instanceof APITimeoutError ? 'timeout' : error instanceof APIUserAbortError ? 'cancelled'
        : error instanceof APIError ? 'unavailable' : 'invalid-response',writeAuthorized:false,
        ...(error instanceof APIError && Number.isSafeInteger(error.status) && error.status >= 400 && error.status <= 599 ? {httpStatus:error.status} : {})};
    }
    results.push({id:row.id,origin:row.origin,scenario:row.scenario,language:row.language,expectedPreserved:row.expectedPreserved,
      expectedOmission:row.expected.omission,result:{...result,durationMs:Date.now()-start}});
    await fs.writeFile('/home/node/research/checkpoint.tmp',JSON.stringify({requests,rows:results})+'\n',{mode:0o600});
    await fs.rename('/home/node/research/checkpoint.tmp','/home/node/research/checkpoint.json');
  }
  await frozen.verify();
  await fs.writeFile('/home/node/research/result.json',JSON.stringify({evidence:'real-jev-manually-anchored-request-completeness',manifestSha256:frozen.sha256,
    requests,rows:results,productionWrites:0,adopted:false,heldout:false,humanGold:false,
    limits:['Manual requirement selection is not validated automatic extraction.','Both questions use the same complete resulting bodies with frontmatter removed.','No candidate generation, Memory writes, recall or Harness effects.','Complete covers supplied requirements only; no authorization or privacy classification proof.']})+'\n',{flag:'wx',mode:0o600});
}
console.log(JSON.stringify({mode,samples:prepared.length,productionWrites:0}));
