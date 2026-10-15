/**
 * Explicit-run paid probe: real-model accuracy and real usage for a free request.
 *
 *   TYPESAFE_API_KEY=... bun packages/loop/tests/real-jev-accuracy.ts
 *   TYPESAFE_API_KEY=... bun packages/loop/tests/real-jev-accuracy.ts --met-only
 *
 * What it establishes: for each labelled request, which interval, run limit,
 * stopping segment and message the real decision service chose, its confidence,
 * the model version it reported, the number of HTTP requests, the tokens each
 * request consumed, and the latency. It reports per-question accuracy against the
 * labels, including the cases the service gets wrong, and it measures one real
 * `met` judgment, because a loop with a stopping condition pays for one of those
 * after every settled turn while the plan is resolved once.
 *
 * What it does not establish: accuracy for requests other than these, which are
 * self-selected and not a distribution, and cost in currency, which needs the
 * account's price list. This spends real credits and never prints the credential.
 */
import { readDecisionConfig } from "../src/config.ts";
import { PlanDecisionError, judgeStopCondition, resolveSemanticPlan } from "../src/decide.ts";

interface Labelled {
  request: string;
  interval?: string;
  runs?: number;
  stop?: boolean;
  message?: string;
  /** Planning this request is wrong; a refusal is the documented outcome. */
  refusal?: boolean;
  /** Refusing is acceptable because the request is genuinely ambiguous. */
  refusalOk?: boolean;
}

const CASES: Labelled[] = [
  { request: "check the build every 5 minutes, 3 times", interval: "5m", runs: 3, stop: false, message: "check the build" },
  { request: "run the smoke test every 30 seconds", interval: "30s", stop: false, message: "run the smoke test" },
  { request: "watch the deploy every 12 minutes. stop when it is green", interval: "15m", stop: true, message: "watch the deploy" },
  { request: "report the status every hour", interval: "1h", stop: false, message: "report the status" },
  { request: "check the CI every 15 minutes, 5 times", interval: "15m", runs: 5, stop: false, message: "check the CI" },
  { request: "poll the queue every day", interval: "1d", stop: false, message: "poll the queue" },
  { request: "run the tests every half an hour", interval: "30m", stop: false, message: "run the tests" },
  { request: "check the build every 5 minutes, 20 times", interval: "5m", runs: 20, stop: false, message: "check the build" },
  { request: "watch the logs every minute, 10 times", interval: "1m", runs: 10, stop: false, message: "watch the logs" },
  { request: "review the backlog every 30 minutes. stop when it is empty", interval: "30m", stop: true, message: "review the backlog" },
  { request: "keep the build green", refusal: true },
  { request: "check the deploy every 5 minutes when it is green", interval: "5m", stop: false,
    message: "check the deploy when it is green", refusalOk: true },
];

interface Call {
  inputTokens: number;
  outputTokens: number;
  ms: number;
}

const calls: Call[] = [];
const upstream = globalThis.fetch;

/**
 * Jev bills input tokens only: $0.42 per million at the $5-$20 prepaid packs and
 * $0.25 per million at $100 (jevtypesafeai.com/pricing, read 2026-10-15; the
 * vendor's own page, which typesafe.ai links). Aggregator listings quoting
 * $0.042/M are wrong by ten times. Output tokens are not charged, so they are
 * measured but not priced.
 */
const USD_PER_MILLION_INPUT = 0.42;
const USD_PER_MILLION_INPUT_BULK = 0.25;

function usd(tokens: number, rate: number): number {
  return Number(((tokens / 1_000_000) * rate).toFixed(6));
}

/** Measure every real request without changing what the client receives. */
globalThis.fetch = (async (...args: Parameters<typeof fetch>) => {
  const started = Date.now();
  const response = await upstream(...args);
  let inputTokens = 0;
  let outputTokens = 0;
  try {
    const body = await response.clone().json() as { usage?: { input_tokens?: number; output_tokens?: number } };
    inputTokens = body.usage?.input_tokens ?? 0;
    outputTokens = body.usage?.output_tokens ?? 0;
  } catch {
    // A refusal carries no usage; it is measured as what it consumed: nothing.
  }
  calls.push({ inputTokens, outputTokens, ms: Date.now() - started });
  return response;
}) as typeof fetch;

interface Row {
  request: string;
  ok: boolean;
  failure?: string;
  interval?: string;
  runs?: string;
  stop?: string;
  message?: string;
  confidence?: { interval: number; runs: number; stop: number; message: number | null };
  model?: string;
  requests: number;
  inputTokens: number;
  outputTokens: number;
  ms: number;
  verdict?: string;
}

function verdictOf(labeled: Labelled, row: Row): string {
  if (labeled.refusal) return row.ok ? "wrong: planned a request that names no cadence" : "right: refused as unplanned";
  if (!row.ok) return labeled.refusalOk ? "right: refused rather than guessed" : "wrong: refused a request it should plan";
  const wrong: string[] = [];
  if (labeled.interval !== undefined && row.interval !== labeled.interval) wrong.push(`interval ${row.interval} != ${labeled.interval}`);
  const runs = row.runs === undefined || row.runs === "unbounded" ? undefined : Number(row.runs);
  if (labeled.runs !== undefined && runs !== labeled.runs) wrong.push(`runs ${row.runs} != ${labeled.runs}`);
  if (labeled.stop !== undefined && (row.stop !== "none") !== labeled.stop) wrong.push(`stop ${row.stop}`);
  if (labeled.message !== undefined && row.message !== labeled.message) wrong.push(`message ${JSON.stringify(row.message)} != ${JSON.stringify(labeled.message)}`);
  return wrong.length === 0 ? "right" : wrong.join("; ");
}

function measured(from: number, started: number): { requests: number; inputTokens: number; outputTokens: number; ms: number } {
  const slice = calls.slice(from);
  return {
    requests: slice.length,
    inputTokens: slice.reduce((total, call) => total + call.inputTokens, 0),
    outputTokens: slice.reduce((total, call) => total + call.outputTokens, 0),
    ms: Date.now() - started,
  };
}

async function runCases(config: NonNullable<ReturnType<typeof readDecisionConfig>>): Promise<Row[]> {
  const rows: Row[] = [];
  for (const labeled of CASES) {
    const from = calls.length;
    const started = Date.now();
    const row: Row = { request: labeled.request, ok: false, requests: 0, inputTokens: 0, outputTokens: 0, ms: 0 };
    try {
      const resolved = await resolveSemanticPlan(labeled.request, { config });
      const report = resolved.report;
      row.ok = true;
      row.interval = report?.interval.key;
      row.runs = report?.runs.key;
      row.stop = report?.stop.key;
      row.message = resolved.plan.message;
      row.model = report?.model;
      row.confidence = report === undefined ? undefined : {
        interval: report.interval.confidence,
        runs: report.runs.confidence,
        stop: report.stop.confidence,
        message: report.message?.confidence ?? null,
      };
    } catch (error) {
      row.failure = error instanceof PlanDecisionError ? `${error.failure}: ${error.message}` : String(error);
    }
    Object.assign(row, measured(from, started));
    row.verdict = verdictOf(labeled, row);
    rows.push(row);
    console.log(JSON.stringify(row));
  }
  return rows;
}

async function measureStopJudgment(config: NonNullable<ReturnType<typeof readDecisionConfig>>): Promise<void> {
  const from = calls.length;
  const started = Date.now();
  const result = await judgeStopCondition({
    config,
    condition: "the deploy is green",
    lastAssistantMessage: "Deployment 4821 is live: the health check returns 200 and the canary stayed green for ten minutes.",
  });
  console.log(JSON.stringify({ metJudgment: { ...measured(from, started), met: result.met, probability: result.probability } }));
}

function summarize(rows: Row[], metCost: ReturnType<typeof measured>, met: { met: boolean; probability: number }): Record<string, unknown> {
  const labeledFor = (row: Row): Labelled | undefined => CASES.find((entry) => entry.request === row.request);
  const right = rows.filter((row) => (row.verdict ?? "").startsWith("right"));
  const of = (key: "interval" | "runs" | "stop"): string => {
    // A case whose label accepts a refusal is not evidence about question
    // accuracy: it is excluded rather than counted as a miss.
    const asked = rows.filter((row) => {
      const labeled = labeledFor(row);
      return labeled?.[key] !== undefined && labeled.refusalOk !== true;
    });
    const hit = asked.filter((row) => {
      if (!row.ok) return false;
      const labeled = labeledFor(row) as Labelled;
      if (key === "runs") return (row.runs === "unbounded" ? undefined : Number(row.runs)) === labeled.runs;
      if (key === "stop") return (row.stop !== "none") === labeled.stop;
      return row[key] === labeled[key];
    });
    return `${hit.length}/${asked.length}`;
  };
  const latency = rows.map((row) => row.ms).sort((left, right_) => left - right_);
  const planTokens = Math.round(rows.reduce((total, row) => total + row.inputTokens, 0) / rows.length);
  const ticksPerDay = 96; // one tick every 5 minutes for eight hours
  const judgmentTokens = metCost.inputTokens * ticksPerDay;
  return {
    cases: rows.length,
    right: right.length,
    wrong: rows.length - right.length,
    intervalRight: of("interval"),
    runsRight: of("runs"),
    stopRight: of("stop"),
    model: rows.find((row) => row.model !== undefined)?.model,
    planInputTokensPerCase: planTokens,
    medianMs: latency[Math.floor(latency.length / 2)],
    maxMs: latency[latency.length - 1],
    metJudgment: { ...metCost, met: met.met, probability: met.probability },
    cost: {
      rateUsdPerMillionInputTokens: USD_PER_MILLION_INPUT,
      bulkRateUsdPerMillionInputTokens: USD_PER_MILLION_INPUT_BULK,
      planUsd: usd(planTokens, USD_PER_MILLION_INPUT),
      metJudgmentUsd: usd(metCost.inputTokens, USD_PER_MILLION_INPUT),
      outputTokensUsd: 0,
      source: "jevtypesafeai.com/pricing, read 2026-10-15; output is not charged",
    },
    eightHourLoopAtFiveMinutes: {
      ticks: ticksPerDay,
      planTokensOnce: planTokens,
      judgedConditionTokens: judgmentTokens,
      usd: Number((usd(planTokens, USD_PER_MILLION_INPUT) + usd(judgmentTokens, USD_PER_MILLION_INPUT)).toFixed(6)),
      usdBulkRate: Number((usd(planTokens, USD_PER_MILLION_INPUT_BULK) + usd(judgmentTokens, USD_PER_MILLION_INPUT_BULK)).toFixed(6)),
      note: "the plan is resolved once; each settled turn with a stopping condition costs one met judgment, and a loop without a stopping condition costs nothing after the plan",
    },
  };
}

/** Recompute the summary from a saved run, which costs nothing. */
function fromSaved(path: string): void {
  const rows: Row[] = [];
  let metCost: ReturnType<typeof measured> = { requests: 0, inputTokens: 0, outputTokens: 0, ms: 0 };
  let met = { met: false, probability: 0 };
  for (const line of require("node:fs").readFileSync(path, "utf8").split("\n")) {
    if (!line.trim()) continue;
    const parsed = JSON.parse(line) as Record<string, unknown>;
    if (parsed.summary) {
      const saved = parsed.summary as { metJudgment?: Record<string, unknown> };
      if (saved.metJudgment) {
        metCost = { requests: Number(saved.metJudgment.requests), inputTokens: Number(saved.metJudgment.inputTokens),
                    outputTokens: Number(saved.metJudgment.outputTokens), ms: Number(saved.metJudgment.ms) };
        met = { met: Boolean(saved.metJudgment.met), probability: Number(saved.metJudgment.probability) };
      }
      continue;
    }
    if (parsed.metJudgment) {
      metCost = { requests: Number(parsed.requests), inputTokens: Number(parsed.inputTokens),
                  outputTokens: Number(parsed.outputTokens), ms: Number(parsed.ms) };
      met = { met: Boolean(parsed.met), probability: Number(parsed.probability) };
      continue;
    }
    rows.push(parsed as unknown as Row);
  }
  console.log(JSON.stringify({ summary: summarize(rows, metCost, met) }));
}

async function main(): Promise<void> {
  const config = readDecisionConfig();
  if (config === undefined) {
    console.log(JSON.stringify({ error: "TYPESAFE_API_KEY is not set; this probe spends real credits and does nothing without it" }));
    return;
  }
  const fromIndex = process.argv.indexOf("--from");
  if (fromIndex > -1) {
    const path = process.argv[fromIndex + 1];
    if (path === undefined) throw new Error("--from needs a saved run path");
    fromSaved(path);
    return;
  }
  if (process.argv.includes("--met-only")) {
    await measureStopJudgment(config);
    return;
  }
  const rows = await runCases(config);
  const metFrom = calls.length;
  const metStarted = Date.now();
  const met = await judgeStopCondition({
    config,
    condition: "the deploy is green",
    lastAssistantMessage: "Deployment 4821 is live: the health check returns 200 and the canary stayed green for ten minutes.",
  });
  const metCost = measured(metFrom, metStarted);
  console.log(JSON.stringify({ summary: summarize(rows, metCost, met) }));
}

await main();