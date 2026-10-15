/**
 * Decision-surface harness for /loop.
 *
 * One loopback endpoint answers like the real service. Nothing inside the
 * transport is stubbed, so the behavior under test is the behavior a real
 * endpoint exercises. Each scenario prints one line of JSON.
 */
import { readDecisionConfig, type DecisionConfig } from "../src/config.ts";
import { judgeStopCondition, PlanDecisionError, resolveSemanticPlan } from "../src/decide.ts";

const scenario = process.argv[2] ?? "semantic-plan";
const REQUEST = "check the deploy every 10 minutes. stop when it is green";
const hits: number[] = [];
const seen: Record<string, unknown>[] = [];

function choice(key: string, confidence: number): Record<string, unknown> {
  const probabilities: Record<string, number> = {};
  probabilities[key] = confidence;
  return { type: "choice", choice: key, probabilities, confidence };
}

function noul(value: number): Record<string, unknown> {
  return { type: "noul", noul: value };
}

function answer(body: Record<string, unknown>): Record<string, unknown> {
  const questions = body.questions as Record<string, unknown>;
  const ids = Object.keys(questions);
  if (ids.includes("met")) {
    return { model: "jev-1.13.0", answers: { met: noul(scenario === "stop-met" ? 0.92 : 0.3) }, usage: { input_tokens: 5, output_tokens: 1 } };
  }
  if (ids.includes("message")) {
    return { model: "jev-1.13.0", answers: { message: choice("without_schedule_and_stop", 0.7) }, usage: { input_tokens: 7, output_tokens: 2 } };
  }
  if (scenario === "count-segment") {
    return {
      model: "jev-1.13.0",
      answers: { interval: choice("5m", 0.9), runs: choice("3", 0.9), stop: choice("none", 0.9) },
      usage: { input_tokens: 11, output_tokens: 4 },
    };
  }
  return {
    model: "jev-1.13.0",
    answers: {
      interval: choice("5m", 0.7),
      runs: choice("unbounded", 0.8),
      stop: choice(scenario === "single-candidate" ? "none" : "segment_1", 0.6),
    },
    usage: { input_tokens: 11, output_tokens: 4 },
  };
}

const server = Bun.serve({
  port: 0,
  async fetch(request) {
    hits.push(1);
    const body = await request.json() as Record<string, unknown>;
    seen.push(body);
    if (scenario === "unauthorized") return new Response("nope", { status: 401 });
    if (scenario === "low-confidence") {
      return Response.json({
        model: "jev-1.13.0",
        answers: { interval: choice("5m", 0.1), runs: choice("unbounded", 0.9), stop: choice("none", 0.9) },
      });
    }
    if (scenario === "unspecified-interval") {
      return Response.json({
        model: "jev-1.13.0",
        answers: { interval: choice("unspecified", 0.9), runs: choice("unbounded", 0.9), stop: choice("none", 0.9) },
      });
    }
    if (scenario === "malformed-choice") {
      return Response.json({
        model: "jev-1.13.0",
        answers: { interval: choice("banana", 0.9), runs: choice("unbounded", 0.9), stop: choice("none", 0.9) },
      });
    }
    return Response.json(answer(body));
  },
});

const base = readDecisionConfig({ TYPESAFE_API_KEY: "test-key" });
if (base === undefined) throw new Error("a test key must read as configured");
const config: DecisionConfig = { ...base, baseUrl: "http://127.0.0.1:" + server.port, stopThreshold: 0.8, minChoiceConfidence: 0.3 };

async function main(): Promise<unknown> {
  if (scenario === "no-credential") return { config: readDecisionConfig({}) ?? null };
  if (scenario === "stop-met" || scenario === "stop-not-met") {
    return await judgeStopCondition({
      config,
      condition: "the deploy is green",
      lastAssistantMessage: "The deploy is green in production.",
    });
  }
  return await resolveSemanticPlan(
    scenario === "single-candidate" ? "check the build"
      : scenario === "count-segment" ? "check the build every 5 minutes, 3 times"
      : REQUEST,
    { config, now: new Date(2026, 0, 2, 3, 4, 5) },
  );
}

try {
  const result = await main();
  const payload = result as Record<string, unknown>;
  console.log(JSON.stringify({
    scenario,
    ok: true,
    plan: payload.plan ?? null,
    mode: payload.mode ?? null,
    report: payload.report ?? null,
    verdict: payload.verdict ?? (payload.met === undefined ? null : result),
    config: payload.config ?? null,
    hits: hits.length,
    requests: seen,
  }));
} catch (error) {
  console.log(JSON.stringify({
    scenario,
    ok: false,
    failure: error instanceof PlanDecisionError ? error.failure : "unexpected",
    message: error instanceof Error ? error.message : String(error),
    hits: hits.length,
  }));
} finally {
  server.stop(true);
}
