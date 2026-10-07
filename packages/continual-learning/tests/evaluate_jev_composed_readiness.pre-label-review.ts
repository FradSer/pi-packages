/** Frozen read-only actual-support comparison; never invokes a writer. */
import fs from 'node:fs/promises';
import {createHash} from 'node:crypto';
import {TypeSafeClient} from '@typesafe-ai/sdk';
import {createJevJudge, type JevTelemetry, type JevCandidateReview} from '../extensions/jev-learning';
import {normalizeNewMemoryProposals} from '../extensions/consolidation-run';
import {readFrozenResearchManifest} from './frozen-research-manifest';
import {ensureMemoryPairResearchPreflight} from './jev-memory-pair-judgment';
import {standaloneMemoryState, standaloneMemoryQuestion, interpretStandaloneMemory} from './jev-standalone-memory-research';
import {simulateIndependentMemorySubset} from './independent-memory-subset-research';
import {simulateComposedMemoryReadiness} from './jev-composed-readiness-research';

interface Sample {id: string; snapshot: unknown; candidates: unknown[]; allowedUsefulSets: number[][]; unsupportedFactIndexes: number[]}
interface Manifest {codeHashes: Record<string,string>; corpus: string; corpusSha256: string; model: string; sdkVersion: string; requestBudget: number}
const live = process.argv.includes('--live');
if (live === process.argv.includes('--preflight-only')) throw new Error('Choose explicit research mode');
const base = new URL('./', import.meta.url);
const hash = (value: unknown) => createHash('sha256').update(JSON.stringify(value)).digest('hex');
const frozen = await readFrozenResearchManifest<Manifest>(new URL('jev-composed-readiness-study-manifest.json', base));
const manifest = frozen.value;
const bytes = await fs.readFile(new URL(manifest.corpus, base));
if (createHash('sha256').update(bytes).digest('hex') !== manifest.corpusSha256) throw new Error('Frozen composed corpus changed');
const samples: Sample[] = JSON.parse(bytes.toString('utf8'));
const sdk = JSON.parse(await fs.readFile(new URL('../node_modules/@typesafe-ai/sdk/package.json', base), 'utf8'));
if (samples.length !== 16 || new Set(samples.map(sample => sample.id)).size !== 16 || manifest.requestBudget !== 80
  || manifest.model !== 'jev-1.13.0' || manifest.sdkVersion !== '0.6.0' || sdk.version !== manifest.sdkVersion) throw new Error('Invalid fixed composed study bounds');
let preflightFixtureRequests = 0;
for (const sample of samples) {
  if (sample.candidates.length !== 2 || JSON.stringify(normalizeNewMemoryProposals({newMemories: sample.candidates}, sample.snapshot)) !== JSON.stringify(sample.candidates)) throw new Error('Original candidate bytes changed');
  preflightFixtureRequests += await ensureMemoryPairResearchPreflight(sample.snapshot, sample.candidates);
}
if (live && !process.env.TYPESAFE_API_KEY) throw new Error('Real composed inference needs host credential');
const output = new URL(`jev-composed-readiness-${live ? 'real-results' : 'preflight'}.json`, base);
const reservation = await fs.open(new URL(output.href + '.reservation'), 'wx');
await reservation.writeFile(JSON.stringify({manifestSha256: frozen.sha256, requestBudget: 80, startedAt: new Date().toISOString()}));
await reservation.close();
interface Request {questionIds: string[]; durationMs: number; responseReceived: boolean; model?: string; inputTokens?: number; outputTokens?: number}
const requests: Request[] = [];
const boundedFetch: typeof fetch = async (url, init) => {
  const wire = String(init?.body);
  const payload = JSON.parse(wire);
  if (requests.length >= 80 || Buffer.byteLength(wire) > 64000 || payload.model !== manifest.model) throw new Error('Composed request bounds exceeded');
  const started = Date.now();
  const request: Request = {questionIds: Object.keys(payload.questions), durationMs: 0, responseReceived: false};
  requests.push(request);
  try {
    let response: Response;
    if (live) response = await fetch(url, init);
    else {
      const answers = Object.fromEntries(Object.entries(payload.questions).map(([key, value]) => {
        const labels = Object.keys((value as {criteria: Record<string,string>}).criteria);
        const choice = key === 'ready' ? 'selfContained' : key === 'relation' ? 'independent' : key.startsWith('supported') ? 'grounded' : 'compatible';
        if (!labels.includes(choice)) throw new Error('Invalid offline question fixture');
        return [key, {type: 'choice', choice, confidence: 1, probabilities: Object.fromEntries(labels.map(label => [label, Number(label === choice)]))}];
      }));
      response = new Response(JSON.stringify({model: manifest.model, answers, usage: {input_tokens: 0, output_tokens: 0}}));
    }
    request.responseReceived = true;
    try {
      const body = await response.clone().json();
      if (body.model === manifest.model) request.model = body.model;
      if (Number.isSafeInteger(body.usage?.input_tokens) && body.usage.input_tokens >= 0) request.inputTokens = body.usage.input_tokens;
      if (Number.isSafeInteger(body.usage?.output_tokens) && body.usage.output_tokens >= 0) request.outputTokens = body.usage.output_tokens;
    } catch { /* Unknown response usage remains unknown, never free. */ }
    return response;
  } finally { request.durationMs = Date.now() - started; }
};
const config = {apiKey: live ? process.env.TYPESAFE_API_KEY : 'fixture-only', defaultModel: manifest.model, timeout: 5000, retry: {maxRetries: 0}, logLevel: 'off' as const, fetch: boundedFetch};
const judge = createJevJudge({...config, enabled: true, scopes: ['memory'], allowPrivateMemory: false});
const client = new TypeSafeClient(config);
interface StudyRow {id: string; completeInference: boolean; allowedUsefulSets: number[][]; unsupportedFactIndexes: number[];
  original: Awaited<ReturnType<typeof simulateIndependentMemorySubset>>;
  composed: Awaited<ReturnType<typeof simulateComposedMemoryReadiness>>;
  support: JevTelemetry; candidateReview?: JevCandidateReview; relations: JevTelemetry; standalone: unknown}
const rows: StudyRow[] = [];
for (const sample of samples) {
  const support = await judge.validate('memory', sample.snapshot, sample.candidates, []);
  const relations = await judge.reviewMemoryRelations(sample.snapshot, sample.candidates, [], support.candidateReview);
  const binding = {evidenceDigest: hash(sample.snapshot), existingDigest: hash([]), candidatesDigest: hash(sample.candidates)};
  const observations = support.candidateReview && relations.review ? await Promise.all(sample.candidates.map(async (candidate, index) => {
    try {
      const response = await client.systemOne({model: manifest.model, state: JSON.stringify(standaloneMemoryState(sample.snapshot, sample.candidates, index)), questions: {ready: standaloneMemoryQuestion()}});
      const interpreted = interpretStandaloneMemory(response.answers.ready);
      if (response.model !== manifest.model || Object.keys(response.answers).length !== 1 || !Object.hasOwn(response.answers, 'ready')
        || interpreted.status === 'invalid-response' || !Number.isSafeInteger(response.usage.input_tokens) || response.usage.input_tokens < 0
        || !Number.isSafeInteger(response.usage.output_tokens) || response.usage.output_tokens < 0) return null;
      return {index, candidateDigest: hash(candidate), answer: {type: 'choice', choice: interpreted.relation, confidence: interpreted.confidence, probabilities: interpreted.probabilities}};
    } catch { return null; }
  })) : [];
  const standalone = observations.length === 2 && observations.every(Boolean)
    ? {version: 1, purpose: 'diagnostic-only', complete: true, model: manifest.model, ...binding, candidates: observations} : undefined;
  const input = {evidence: sample.snapshot, candidates: sample.candidates, existing: [], operations: [], review: support.candidateReview,
    pairs: (relations.review?.pairs ?? []).map(pair => ({...pair, model: manifest.model, ...binding})), windows: support.telemetry.evidenceWindows ?? 0, allowPrivateMemory: false};
  const original = await simulateIndependentMemorySubset(input);
  const composed = await simulateComposedMemoryReadiness(input, standalone);
  rows.push({id: sample.id, completeInference: !!(support.candidateReview && relations.review && standalone), allowedUsefulSets: sample.allowedUsefulSets, unsupportedFactIndexes: sample.unsupportedFactIndexes,
    original, composed, support: support.telemetry, candidateReview: support.candidateReview, relations: relations.telemetry, standalone});
  await fs.writeFile(new URL(output.href + '.checkpoint.tmp'), JSON.stringify({requests, rows}, null, 2) + '\n');
  await fs.rename(new URL(output.href + '.checkpoint.tmp'), new URL(output.href + '.checkpoint'));
}
await frozen.verify();
if (createHash('sha256').update(await fs.readFile(new URL(manifest.corpus, base))).digest('hex') !== manifest.corpusSha256) throw new Error('Composed corpus changed during inference');
const metrics = Object.fromEntries((['original','composed'] as const).map(arm => [arm, {
  usefulKnowledgeCases: rows.filter(row => row.allowedUsefulSets.some(set => set.length > 0 && JSON.stringify(set) === JSON.stringify(row[arm].recoverable))).length,
  requiredKnowledgeHeldCases: rows.filter(row => row.allowedUsefulSets.every(set => set.length > 0) && !row.allowedUsefulSets.some(set => JSON.stringify(set) === JSON.stringify(row[arm].recoverable))).length,
  unsupportedFactSelections: rows.reduce((sum,row) => sum + row[arm].recoverable.filter(index => row.unsupportedFactIndexes.includes(index)).length, 0),
  unsafeCandidateSelections: rows.reduce((sum,row) => sum + row[arm].recoverable.filter(index => !row.allowedUsefulSets.some(set => set.includes(index))).length, 0),
  incompatibleOrRedundantSelections: rows.filter(row => row[arm].recoverable.every(index => row.allowedUsefulSets.some(set => set.includes(index)))
    && !row.allowedUsefulSets.some(set => row[arm].recoverable.every(index => set.includes(index)))).length,
  originalSuccessesLost: arm === 'original' ? 0 : rows.filter(row => row.original.recoverable.some(index => !row.composed.recoverable.includes(index))).length
}]));
const knownInputTokens = requests.reduce((sum, request) => sum + (request.inputTokens ?? 0), 0);
const pricedInputTokens = requests.reduce((sum, request) => sum + (request.model === manifest.model ? request.inputTokens ?? 0 : 0), 0);
await fs.writeFile(output, JSON.stringify({evidence: live ? 'real-jev-fresh-composed-selection-simulation' : 'offline-fixture-preflight', manifestSha256: frozen.sha256,
  externalRequests: live ? requests.length : 0, fixtureRequests: live ? 0 : requests.length, preflightFixtureRequests, requestBudget: 80, metrics,
  incompleteInferenceCases: rows.filter(row => !row.completeInference).length, knownInputTokens, unpricedInputTokens: knownInputTokens - pricedInputTokens,
  estimatedKnownInputCostUsd: pricedInputTokens * .042 / 1000000, usageComplete: requests.every(request => request.inputTokens !== undefined && request.outputTokens !== undefined),
  remoteCompletionUnknown: requests.some(request => !request.responseReceived), requests, rows, productionWrites: 0, adopted: false,
  limitations: ['Actual semantic support/pair/readiness; read-only simulation, not application or recall.', 'Eight author-defined bilingual archetypes; independent review is not blind labeling.', 'Identical support/pair observations shared by both arms, not independent main model generations.', 'Offline fixture metrics are not real effectiveness.']}, null, 2) + '\n', {flag: 'wx'});
console.log(JSON.stringify({live, requests: requests.length, metrics, knownInputTokens}));
