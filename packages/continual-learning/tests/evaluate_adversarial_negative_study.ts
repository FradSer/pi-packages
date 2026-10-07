/**
 * Read-only adversarial negative study against the production Jev judge.
 *
 * No Memory or Harness write happens here: every judgment is a read-only
 * `validate` call and the result grants no authority. The corpus is frozen by
 * content hash before the first paid call.
 *
 * Usage:
 *   bun evaluate_adversarial_negative_study.ts --preflight-only <cases.json> <rawRoot>
 *   bun evaluate_adversarial_negative_study.ts --live <cases.json> <rawRoot>
 */
import { createHash } from 'node:crypto';
import fs from 'node:fs';
import path from 'node:path';
import { containsSensitiveMemoryMaterial } from '../extensions/consolidation-run';
import { createJevJudge } from '../extensions/jev-learning';

const MODEL = 'jev-1.13.0';
const REQUEST_BUDGET = 40;
const MAX_SAMPLE_BYTES = 24_000;
const DEFAULT_CLASSES = ['speculation', 'transient-failure', 'revocation', 'duplicate', 'supplement', 'conflict', 'harness-scope-expansion'];

interface Case {
  id: string;
  class: string;
  language: string;
  direction: 'memory' | 'harness';
  expected: 'allow' | 'hold';
  evidence: unknown;
  candidate?: { name: string; content: string };
  rule?: unknown;
  existing: unknown[];
}

const [mode, corpusPath, rawRoot] = process.argv.slice(2);
if (!['--preflight-only', '--live'].includes(mode ?? '') || !corpusPath || !rawRoot) {
  throw new Error('Mode, corpus path, and raw root are required');
}
const corpusBytes = fs.readFileSync(corpusPath);
const corpusSha = createHash('sha256').update(corpusBytes).digest('hex');
const shaPath = `${corpusPath}.sha256`;
fs.mkdirSync(rawRoot, { recursive: true, mode: 0o700 });
if (fs.existsSync(shaPath)) {
  const recorded = fs.readFileSync(shaPath, 'utf8').trim();
  if (recorded !== corpusSha) throw new Error('Frozen corpus changed');
} else {
  fs.writeFileSync(shaPath, `${corpusSha}\n`, { mode: 0o600 });
}

const corpus = JSON.parse(corpusBytes.toString()) as { model: string; requestBudget: number; cases: Case[]; expectedCases?: number; classes?: string[] };
if (corpus.model !== MODEL) throw new Error('Model pin changed');
if (corpus.requestBudget !== REQUEST_BUDGET) throw new Error('Request budget pin changed');
const cases = corpus.cases;
const CLASSES = corpus.classes ?? DEFAULT_CLASSES;
if (corpus.expectedCases !== undefined && cases.length !== corpus.expectedCases) throw new Error('Sample count changed');
if (new Set(cases.map(item => item.id)).size !== cases.length) throw new Error('Duplicate sample id');
if (new Set(cases.map(item => item.class)).size !== CLASSES.length) throw new Error('Class set changed');
if (new Set(cases.map(item => item.language)).size !== 2) throw new Error('Language set changed');

const sampleBody = (item: Case): string =>
  item.direction === 'memory'
    ? JSON.stringify({ evidence: item.evidence, candidates: [item.candidate], existing: item.existing })
    : JSON.stringify({ evidence: item.evidence, candidates: [item.rule], existing: item.existing });

for (const item of cases) {
  if (!CLASSES.includes(item.class)) throw new Error(`Unknown class: ${item.class}`);
  if (!['en', 'zh'].includes(item.language)) throw new Error(`Unknown language: ${item.language}`);
  if (!['memory', 'harness'].includes(item.direction)) throw new Error(`Unknown direction: ${item.direction}`);
  if (!['allow', 'hold'].includes(item.expected)) throw new Error(`Unknown label: ${item.expected}`);
  if (item.direction === 'memory' && !item.candidate) throw new Error(`Missing candidate: ${item.id}`);
  if (item.direction === 'harness' && !item.rule) throw new Error(`Missing rule: ${item.id}`);
  const body = sampleBody(item);
  if (Buffer.byteLength(body, 'utf8') > MAX_SAMPLE_BYTES) throw new Error(`Sample exceeds the window bound: ${item.id}`);
  if (containsSensitiveMemoryMaterial(body)) throw new Error(`Sample trips the privacy guard: ${item.id}`);
}

if (mode === '--preflight-only') {
  fs.writeFileSync(
    path.join(rawRoot, 'preflight.json'),
    `${JSON.stringify({
      corpusSha256: corpusSha,
      cases: cases.length,
      classes: [...new Set(cases.map(item => item.class))].length,
      languages: [...new Set(cases.map(item => item.language))].sort(),
      labelsFrozen: true,
      externalRequests: 0,
      productionWrites: 0,
      model: MODEL,
      requestBudget: REQUEST_BUDGET,
    }, null, 2)}\n`,
    { mode: 0o600 },
  );
  console.log(JSON.stringify({ mode: 'preflight', cases: cases.length, corpusSha256: corpusSha, externalRequests: 0 }));
} else {
  const apiKey = process.env.TYPESAFE_API_KEY;
  if (!apiKey) throw new Error('Live mode requires TYPESAFE_API_KEY');
  let requests = 0;
  const judge = createJevJudge({
    enabled: true,
    defaultModel: MODEL,
    scopes: ['memory', 'harness'],
    apiKey,
    timeout: 5_000,
    retry: { maxRetries: 0 },
    fetch: async (url: string | URL | Request, init?: RequestInit) => {
      requests += 1;
      if (requests > REQUEST_BUDGET) throw new Error('Request budget exceeded');
      return fetch(url as RequestInfo, init);
    },
  } as Parameters<typeof createJevJudge>[0]);

  const resultsPath = path.join(rawRoot, 'results.json');
  const rows: Record<string, unknown>[] = [];
  for (const item of cases) {
    const started = Date.now();
    let validation: Record<string, unknown>;
    try {
      const judged = item.direction === 'memory'
        ? await judge.validate('memory', item.evidence, [item.candidate as Record<string, unknown>], item.existing as Record<string, unknown>[])
        : await judge.validate('harness', item.evidence, [item.rule as Record<string, unknown>], item.existing as Record<string, unknown>[]);
      const telemetry = (judged as { telemetry: Record<string, unknown> }).telemetry;
      const decision = (judged as { decision: string }).decision;
      // Record controlled answer fields only: a question key, its type, the chosen
      // label, the confidence, the probability map, and a noul value. Never raw
      // model text, criteria, or candidate content.
      const answerMap = (judged as { result?: { answers?: Record<string, { type?: string; choice?: string; confidence?: number; probabilities?: Record<string, number>; noul?: number }> } }).result?.answers ?? {};
      const answers = Object.fromEntries(Object.entries(answerMap).map(([key, value]) => [key, {
        type: value?.type, choice: value?.choice, confidence: value?.confidence, probabilities: value?.probabilities, noul: value?.noul,
      }]));
      validation = {
        decision,
        matchesLabel: (item.expected === 'allow' && decision === 'allow') || (item.expected === 'hold' && decision !== 'allow'),
        falseAllow: item.expected === 'hold' && decision === 'allow',
        falseHold: item.expected === 'allow' && decision !== 'allow',
        telemetry: {
          status: telemetry["status"], reason: telemetry["reason"], model: telemetry["model"],
          durationMs: telemetry["durationMs"], requestCount: telemetry["requestCount"],
          completedRequests: telemetry["completedRequests"], retriedRequests: telemetry["retriedRequests"],
          failureKind: telemetry["failureKind"], httpStatus: telemetry["httpStatus"],
          inputTokens: telemetry["inputTokens"], outputTokens: telemetry["outputTokens"],
          estimatedCostUsd: telemetry["estimatedCostUsd"], evidenceWindows: telemetry["evidenceWindows"],
          completedWindows: telemetry["completedWindows"], candidateFailures: telemetry["candidateFailures"],
        },
        answers,
      };
    } catch (error) {
      validation = { decision: 'error', matchesLabel: false, falseAllow: false, falseHold: false, errorKind: (error as Error).name };
    }
    rows.push({
      id: item.id, class: item.class, language: item.language, direction: item.direction, expected: item.expected,
      wallMs: Date.now() - started, ...validation,
    });
    const temporary = `${resultsPath}.tmp`;
    fs.writeFileSync(temporary, `${JSON.stringify({ corpusSha256: corpusSha, model: MODEL, requests, rows }, null, 2)}\n`, { mode: 0o600 });
    fs.renameSync(temporary, resultsPath);
  }
  const falseAllows = rows.filter(row => row['falseAllow']).length;
  const falseHolds = rows.filter(row => row['falseHold']).length;
  const matched = rows.filter(row => row['matchesLabel']).length;
  console.log(JSON.stringify({ mode: 'live', cases: rows.length, matched, falseAllows, falseHolds, requests, corpusSha256: corpusSha }));
}