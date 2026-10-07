/** Prospective complete-batch research; no plans, writes, or main-model calls. */
import fs from 'node:fs/promises';
import {createHash} from 'node:crypto';
import {TypeSafeClient, APIError, APITimeoutError, APIUserAbortError} from '@typesafe-ai/sdk';
import {createJevJudge} from '../extensions/jev-learning';
import {normalizeNewMemoryProposals} from '../extensions/consolidation-run';
import type {SelectedMemory} from '../extensions/incremental-learning';
import {readFrozenResearchManifest} from './frozen-research-manifest';
import {structuredMemoryPairQuestion, structuredMemoryPairState} from './jev-memory-pair-structured';
import {interpretMemoryPair} from './jev-memory-pair-judgment';
import {simulateIndependentMemorySubset} from './independent-memory-subset-research';
import {subsetBatchMetrics} from './subset-batch-metrics';

const live = process.argv.includes('--live');
if (live === process.argv.includes('--preflight-only')) throw new Error('Choose explicit research mode');
const base = new URL('./', import.meta.url);
const arg = (key: string): string => {const index = process.argv.indexOf(key); if (index < 0 || !process.argv[index + 1]) throw new Error('Missing research argument'); return process.argv[index + 1];};
interface Sample {id: string; language: string; archetype: string; snapshot: unknown; candidates: unknown[]; existing: SelectedMemory[]; eligible: boolean[]; expectedPairs: Record<string, string>}
interface Manifest {codeHashes: Record<string, string>; corpus: string; corpusSha256: string; model: string; requestBudget: number; paidAllowed: boolean}
const frozen = await readFrozenResearchManifest<Manifest>(new URL('jev-subset-full-batch-development-manifest.json', base));
const m = frozen.value, bytes = await fs.readFile(new URL(m.corpus, base));
const digest = (value: unknown): string => createHash('sha256').update(JSON.stringify(value)).digest('hex');
if (createHash('sha256').update(bytes).digest('hex') !== m.corpusSha256) throw new Error('Frozen corpus changed');
const samples = JSON.parse(bytes.toString('utf8')) as Sample[];
const output = arg('--output');
await fs.writeFile(output + '.reservation', JSON.stringify({manifestSha256: frozen.sha256, live, requestBudget: m.requestBudget}), {flag: 'wx', mode: 0o600});
if (live && (!m.paidAllowed || !process.env.TYPESAFE_API_KEY)) throw new Error('Live research prerequisites missing');
let localPreflightRequests = 0;
for (const row of samples) {
  if (row.eligible.length !== row.candidates.length || row.candidates.length !== 3) throw new Error('Invalid complete batch');
  normalizeNewMemoryProposals({newMemories: row.candidates}, row.snapshot);
  const judge = createJevJudge({enabled: true, apiKey: 'fixture-only', defaultModel: m.model, scopes: ['memory'],
    fetch: async () => {localPreflightRequests++; throw new Error('Offline complete-batch preflight');}});
  const verdict = await judge.validate('memory', row.snapshot, row.candidates, row.existing);
  if (verdict.telemetry.evidenceWindows !== 1) throw new Error('Full batch preflight denied');
  for (let a = 0; a < 3; a++) for (let b = a + 1; b < 3; b++) structuredMemoryPairState(row.snapshot, [row.candidates[a], row.candidates[b]]);
}
let requests = 0;
const responseMetadata: {status: number; model?: string; inputTokens?: number; outputTokens?: number}[] = [];
const transport: typeof fetch = async (url, init) => {
  if (!live || String(url) !== 'https://api.typesafe.ai/v1/systemone' || requests >= m.requestBudget
    || Buffer.byteLength(String(init?.body)) > 64000 || JSON.parse(String(init?.body)).model !== m.model) throw new Error('Research transport denied');
  requests++;
  const response = await fetch(url, init);
  let raw: unknown;
  try {raw = await response.clone().json();} catch {raw = undefined;}
  const object = raw && typeof raw === 'object' ? raw as Record<string, unknown> : undefined;
  const usage = object?.usage as {input_tokens?: number; output_tokens?: number} | undefined;
  const meta = {status: response.status, ...(object?.model === m.model ? {model: m.model} : {}),
    ...(Number.isSafeInteger(usage?.input_tokens) && usage!.input_tokens! >= 0 ? {inputTokens: usage!.input_tokens} : {}),
    ...(Number.isSafeInteger(usage?.output_tokens) && usage!.output_tokens! >= 0 ? {outputTokens: usage!.output_tokens} : {})};
  responseMetadata.push(meta);
  const trace = response.ok && object?.model === m.model ? {model: object.model, answers: object.answers, usage: object.usage} : undefined;
  const privateLine = JSON.stringify({request: JSON.parse(String(init?.body)), response: trace, status: response.status});
  const key = process.env.TYPESAFE_API_KEY;
  await fs.appendFile(output + '.private-responses.jsonl', (key ? privateLine.replaceAll(key, '[redacted]') : privateLine) + '\n', {mode: 0o600});
  return response;
};
const client = new TypeSafeClient({apiKey: process.env.TYPESAFE_API_KEY || 'fixture-only', baseURL: 'https://api.typesafe.ai',
  defaultModel: m.model, timeout: 5000, retry: {maxRetries: 0}, logLevel: 'off', fetch: transport});
const judge = createJevJudge({enabled: true, apiKey: process.env.TYPESAFE_API_KEY || 'fixture-only', baseURL: 'https://api.typesafe.ai',
  defaultModel: m.model, scopes: ['memory'], timeout: 5000, fetch: transport});
const rows = [];
for (const row of samples) {
  if (!live) continue;
  const started = Date.now();
  const verdict = await judge.validate('memory', row.snapshot, row.candidates, row.existing);
  const wholeDurationMs = Date.now() - started;
  const indexes = row.candidates.map((_, index) => index);
  const pairs = verdict.candidateReview ? await Promise.all(indexes.flatMap(a => indexes.filter(b => b > a).map(async b => {
    const state = {...structuredMemoryPairState(row.snapshot, [row.candidates[a], row.candidates[b]]), wholeOriginalCandidates: row.candidates, existingMemories: row.existing};
    try {
      const response = await client.systemOne({model: m.model, state: JSON.stringify(state), questions: {relation: structuredMemoryPairQuestion()}});
      const valid = response.model === m.model && Object.keys(response.answers).length === 1 && Number.isSafeInteger(response.usage.input_tokens) && response.usage.input_tokens >= 0;
      const interpreted = interpretMemoryPair(response.answers.relation);
      return {a, b, model: response.model, evidenceDigest: digest(row.snapshot), existingDigest: digest(row.existing), candidatesDigest: digest(row.candidates),
        candidateDigests: [digest(row.candidates[a]), digest(row.candidates[b])], answer: valid ? response.answers.relation : undefined,
        status: valid ? interpreted.status : 'invalid-response', expected: row.expectedPairs[`${a}:${b}`], relation: interpreted.relation};
    } catch (error) {
      return {a, b, model: '', evidenceDigest: digest(row.snapshot), existingDigest: digest(row.existing), candidatesDigest: digest(row.candidates), candidateDigests: [], answer: undefined,
        status: error instanceof APITimeoutError ? 'timeout' : error instanceof APIUserAbortError ? 'cancelled' : 'unavailable', expected: row.expectedPairs[`${a}:${b}`], relation: null,
        ...(error instanceof APIError && error.status >= 400 && error.status <= 599 ? {httpStatus: error.status} : {})};
    }
  }))) : [];
  const simulation = await simulateIndependentMemorySubset({evidence: row.snapshot, candidates: row.candidates, existing: row.existing,
    operations: [], review: verdict.candidateReview, pairs, windows: verdict.telemetry.evidenceWindows ?? 0});
  rows.push({id: row.id, language: row.language, archetype: row.archetype, eligible: row.eligible,
    whole: verdict.decision === 'allow' ? indexes : [], subset: verdict.decision === 'allow' ? indexes : simulation.recoverable, simulation,
    review: verdict.candidateReview, telemetry: verdict.telemetry, pairs, wholeDurationMs, durationMs: Date.now() - started});
  await fs.writeFile(output + '.checkpoint.tmp', JSON.stringify({requests, rows, responseMetadata}), {mode: 0o600});
  await fs.rename(output + '.checkpoint.tmp', output + '.checkpoint');
}
await frozen.verify();
if (createHash('sha256').update(await fs.readFile(new URL(m.corpus, base))).digest('hex') !== m.corpusSha256) throw new Error('Corpus changed during study');
const metrics = subsetBatchMetrics(rows);
const knownInputTokens = responseMetadata.reduce((sum, row) => sum + (row.inputTokens ?? 0), 0);
const pricedInputTokens = responseMetadata.reduce((sum, row) => sum + (row.model === m.model ? row.inputTokens ?? 0 : 0), 0);
const actualModelComplete = live && requests > 0 && responseMetadata.length === requests && responseMetadata.every(row => row.model === m.model);
const report = {evidence: live ? 'real-jev-complete-batch-subset-research-no-writes' : 'offline-preflight-no-judgment',
  manifestSha256: frozen.sha256, corpusSha256: m.corpusSha256, rows, metrics, externalRequests: requests, localPreflightRequests,
  preparedBatches: samples.length, responseMetadata, knownInputTokens, knownInputTariffEstimateUsd: pricedInputTokens * .042 / 1e6, unpricedInputTokens: knownInputTokens - pricedInputTokens, actualModelComplete,
  usageComplete: responseMetadata.length === requests && responseMetadata.every(row => row.inputTokens !== undefined && row.outputTokens !== undefined),
  productionWrites: 0, mainModelCalls: 0, humanGold: false, heldout: false, adopted: false,
  limits: ['New synthetic authored development batches, not human gold or open-source workflows.', 'Dependency B/C pair labels are ambiguous because B references A; pair labels are diagnostic and are not used in candidate recovery success criteria.', 'Whole-plan and subset arms reuse exactly the same real complete-candidate judgments.',
    'Already allowed whole plans keep their original result; only held plans can gain an independent subset.', 'Independent relations are extra requests; arm cost and latency are not identical.', 'No threshold relaxation, source relabeling or favorable retries.', 'Known tariff estimate is not an invoice; incomplete usage is unknown, not free.']};
await fs.writeFile(output, JSON.stringify(report, null, 2) + '\n', {flag: 'wx', mode: 0o600});
console.log(JSON.stringify({evidence: report.evidence, requests, metrics, knownInputTokens, usageComplete: report.usageComplete}));
