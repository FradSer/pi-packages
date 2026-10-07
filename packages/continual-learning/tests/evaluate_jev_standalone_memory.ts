/** Read-only comparison: original pair observation versus target standalone meaning. */
import fs from 'node:fs/promises';
import {createHash} from 'node:crypto';
import {TypeSafeClient, APIError, APITimeoutError, APIUserAbortError} from '@typesafe-ai/sdk';
import {readFrozenResearchManifest} from './frozen-research-manifest';
import {ensureMemoryPairResearchPreflight} from './jev-memory-pair-judgment';
import {structuredMemoryPairQuestion, structuredMemoryPairState, interpretMemoryPair} from '../extensions/jev-memory-relations';
import {standaloneMemoryState, standaloneMemoryQuestion, interpretStandaloneMemory} from './jev-standalone-memory-research';
import {normalizeNewMemoryProposals} from '../extensions/consolidation-run';

interface Sample {id: string; snapshot: unknown; candidates: unknown[]; targetIndex: number; expectedPairRelation: string; expectedStandalone: string}
interface Manifest {codeHashes: Record<string,string>; corpus: string; corpusSha256: string; model: string; requestBudget: number; sdkVersion: string; timeoutMs: number; retry: number; thresholds: {confidence: number; probability: number}}
const live = process.argv.includes('--live');
if (live === process.argv.includes('--preflight-only')) throw new Error('Choose explicit research mode');
const base = new URL('./', import.meta.url);
const frozen = await readFrozenResearchManifest<Manifest>(new URL('jev-standalone-memory-study-manifest.json', base));
const manifest = frozen.value;
const hash = (bytes: Buffer) => createHash('sha256').update(bytes).digest('hex');
const bytes = await fs.readFile(new URL(manifest.corpus, base));
if (hash(bytes) !== manifest.corpusSha256) throw new Error('Frozen standalone corpus changed');
const samples: Sample[] = JSON.parse(bytes.toString('utf8'));
const sdk = JSON.parse(await fs.readFile(new URL('../node_modules/@typesafe-ai/sdk/package.json', base), 'utf8'));
if (manifest.model !== 'jev-1.13.0' || samples.length !== 16 || manifest.requestBudget !== 32
  || manifest.sdkVersion !== '0.6.0' || sdk.version !== manifest.sdkVersion
  || manifest.timeoutMs !== 5000 || manifest.retry !== 0
  || manifest.thresholds.confidence !== .8 || manifest.thresholds.probability !== .9) throw new Error('Invalid fixed research bounds or SDK version');
let preflightFixtureRequests = 0;
for (const sample of samples) {
  if (sample.candidates.length !== 2 || JSON.stringify(normalizeNewMemoryProposals({newMemories: sample.candidates}, sample.snapshot)) !== JSON.stringify(sample.candidates)) throw new Error('Original candidates changed during normalization');
  preflightFixtureRequests += await ensureMemoryPairResearchPreflight(sample.snapshot, sample.candidates);
}
if (live && !process.env.TYPESAFE_API_KEY) throw new Error('Real standalone inference requires host credential');
const output = new URL(`jev-standalone-memory-${live ? 'real-results' : 'preflight'}.json`, base);
const reservation = await fs.open(new URL(output.href + '.reservation'), 'wx');
await reservation.writeFile(JSON.stringify({manifestSha256: frozen.sha256, requestBudget: manifest.requestBudget, startedAt: new Date().toISOString()}));
await reservation.close();
let requests = 0;
const client = new TypeSafeClient({apiKey: live ? process.env.TYPESAFE_API_KEY : 'fixture-only', defaultModel: manifest.model, timeout: 5000, retry: {maxRetries: 0}, logLevel: 'off',
  fetch: async (url, init) => {
    if (requests >= manifest.requestBudget || Buffer.byteLength(String(init?.body)) > 64000) throw new Error('Standalone study bounds exceeded');
    requests++;
    if (live) return fetch(url, init);
    const question = Object.keys(JSON.parse(String(init?.body)).questions)[0];
    const labels = question === 'pair' ? ['independent','duplicate','conflict','dependent','unclear'] : ['selfContained','needsOther','unresolved'];
    return new Response(JSON.stringify({model: manifest.model, answers: {[question]: {type: 'choice', choice: labels[0], confidence: 1, probabilities: Object.fromEntries(labels.map((label,index) => [label, Number(index === 0)]))}}, usage: {input_tokens: 0, output_tokens: 0}}));
  }});
interface Row {id: string; arm: 'pair' | 'standalone'; expected: string; status: string; relation: string | null; readyObserved: boolean; durationMs: number; model?: string; inputTokens?: number; outputTokens?: number; confidence?: number; probabilities?: unknown; httpStatus?: number}
const rows: Row[] = [];
for (const sample of samples) {
  const batch = await Promise.all((['pair','standalone'] as const).map(async arm => {
    const started = Date.now();
    try {
      const state = arm === 'pair' ? structuredMemoryPairState(sample.snapshot, sample.candidates) : standaloneMemoryState(sample.snapshot, sample.candidates, sample.targetIndex);
      const question = arm === 'pair' ? structuredMemoryPairQuestion() : standaloneMemoryQuestion();
      const response = await client.systemOne({model: manifest.model, state: JSON.stringify(state), questions: {[arm]: question}});
      const answer = response.answers[arm];
      const verdict = arm === 'pair' ? interpretMemoryPair(answer) : interpretStandaloneMemory(answer);
      const validModel = response.model === manifest.model;
      const validUsage = Number.isSafeInteger(response.usage.input_tokens) && response.usage.input_tokens >= 0 && Number.isSafeInteger(response.usage.output_tokens) && response.usage.output_tokens >= 0;
      const validSet = Object.keys(response.answers).length === 1 && Object.hasOwn(response.answers, arm);
      const ready = 'independenceObserved' in verdict ? verdict.independenceObserved : verdict.standaloneObserved;
      return {id: sample.id, arm, expected: arm === 'pair' ? sample.expectedPairRelation : sample.expectedStandalone,
        status: validModel && validUsage && validSet ? verdict.status : 'invalid-response', relation: verdict.relation,
        readyObserved: !!(validModel && validUsage && validSet && ready), durationMs: Date.now() - started,
        ...(validModel ? {model: response.model} : {}), ...(validUsage ? {inputTokens: response.usage.input_tokens, outputTokens: response.usage.output_tokens} : {}),
        confidence: verdict.confidence, probabilities: verdict.probabilities};
    } catch (error) {
      return {id: sample.id, arm, expected: arm === 'pair' ? sample.expectedPairRelation : sample.expectedStandalone,
        status: error instanceof APITimeoutError ? 'timeout' : error instanceof APIUserAbortError ? 'cancelled' : 'unavailable', relation: null, readyObserved: false,
        durationMs: Date.now() - started, ...(error instanceof APIError ? {httpStatus: error.status} : {})};
    }
  }));
  rows.push(...batch);
  await fs.writeFile(new URL(output.href + '.checkpoint.tmp'), JSON.stringify({requests, rows}, null, 2) + '\n');
  await fs.rename(new URL(output.href + '.checkpoint.tmp'), new URL(output.href + '.checkpoint'));
}
await frozen.verify();
if (hash(await fs.readFile(new URL(manifest.corpus, base))) !== manifest.corpusSha256) throw new Error('Standalone corpus changed during inference');
const metrics = Object.fromEntries((['pair','standalone'] as const).map(arm => {
  const selected = rows.filter(row => row.arm === arm);
  const readyLabel = arm === 'pair' ? 'independent' : 'selfContained';
  return [arm, {decisiveCorrect: selected.filter(row => row.status === 'decided' && row.relation === row.expected).length,
    decisiveWrong: selected.filter(row => row.status === 'decided' && row.relation !== row.expected).length,
    held: selected.filter(row => row.status !== 'decided').length,
    unsafeReadiness: selected.filter(row => row.readyObserved && row.expected !== readyLabel).length,
    missedReadiness: selected.filter(row => !row.readyObserved && row.expected === readyLabel).length}];
}));
const knownInputTokens = rows.reduce((sum, row) => sum + (row.inputTokens ?? 0), 0);
await fs.writeFile(output, JSON.stringify({evidence: live ? 'real-jev-readonly-standalone-comparison' : 'offline-fixture-preflight', manifestSha256: frozen.sha256,
  externalRequests: live ? requests : 0, fixtureRequests: live ? 0 : requests, preflightFixtureRequests, requestBudget: manifest.requestBudget,
  metrics, knownInputTokens, estimatedKnownInputCostUsd: knownInputTokens * .042 / 1000000, usageComplete: rows.every(row => row.inputTokens !== undefined),
  rows, productionWrites: 0, adopted: false, limitations: ['Different semantic questions, not interchangeable decisions.', 'Standalone meaning does not prove support, durability, privacy, pair compatibility or write permission.', 'No main generation, application, recall or complete quality acceptance.', 'New author-defined synthetic cases; not independent labels until separately reviewed.']}, null, 2) + '\n', {flag: 'wx'});
console.log(JSON.stringify({live, requests, metrics, knownInputTokens}));
