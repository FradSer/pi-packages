/** Decision-surface harness. One loopback endpoint, several scripted faults.
 *  Nothing inside the transport is stubbed: the behaviors under contract are
 *  exactly the ones a real endpoint exercises. */
import { askSystemOne, DecisionServiceError } from "../src/index.ts";

const scenario = process.argv[2] ?? "answers";
let hits = 0;
let throttlesLeft = scenario === "throttled-once" ? 1 : scenario === "throttled" ? Number.MAX_SAFE_INTEGER : 0;

const server = Bun.serve({
  port: 0,
  fetch(request) {
    hits += 1;
    const url = request.url;
    if (scenario === "unreachable") return new Response("refused", { status: 502 });
    if (throttlesLeft > 0) {
      throttlesLeft -= 1;
      return new Response(JSON.stringify({ error: "slow down" }), {
        status: 429,
        headers: { "content-type": "application/json", "retry-after": "0" },
      });
    }
    if (url.includes("/oversize")) {
      return new Response("{}", { headers: { "content-type": "application/json", "content-length": "99999999" } });
    }
    if (scenario === "unauthorized") return new Response("nope", { status: 401 });
    if (scenario === "missing-answer") {
      return Response.json({ model: "jev-1.13.0", answers: { a: { type: "noul", noul: 0.5 } } });
    }
    if (scenario === "non-object-answer") {
      return Response.json({ model: "jev-1.13.0", answers: { a: 3, b: { type: "noul", noul: 0.5 } } });
    }
    if (scenario === "no-answers") return Response.json({ model: "jev-1.13.0" });
    if (scenario === "not-json") return new Response("not json", { headers: { "content-type": "application/json" } });
    return Response.json({
      model: "jev-1.13.0",
      answers: {
        a: { type: "noul", noul: 0.9 },
        b: { type: "choice", choice: "yes", probabilities: { yes: 0.9, no: 0.1 }, confidence: 0.8 },
      },
      usage: { input_tokens: 12, output_tokens: 5 },
    });
  },
});

const baseUrl = `http://127.0.0.1:${server.port}${scenario === "oversize" ? "/oversize" : ""}`;
// `missing-answer` needs a genuinely multi-question request: a single-question
// set can never have a silently missing answer.
const questions = scenario === "missing-answer"
  ? {
      a: { type: "noul" as const, instructions: "Is it true?" },
      b: { type: "choice" as const, instructions: "Which?", criteria: { yes: null, no: null } },
    }
  : { a: { type: "noul" as const, instructions: "Is it true?" } };

const attempt = async (overrides: Record<string, unknown> = {}) => {
  try {
    const result = await askSystemOne({
      baseUrl,
      apiKey: "k",
      model: "jev-1.13.0",
      state: { x: 1 },
      questions,
      timeoutMs: 5_000,
      retries: 2,
      ...overrides,
    });
    return { ok: true as const, model: result.model, answers: result.answers, usage: result.usage, hits };
  } catch (error) {
    return {
      ok: false as const,
      isDecisionError: error instanceof DecisionServiceError,
      failure: error instanceof DecisionServiceError ? error.failure : `unexpected: ${String(error)}`,
      message: error instanceof Error ? error.message : String(error),
      hits,
    };
  }
};

try {
  let out: unknown;
  if (scenario === "empty-questions") {
    out = await attempt({ questions: {} });
  } else if (scenario === "pre-aborted") {
    out = await attempt({ signal: AbortSignal.abort() });
  } else if (scenario === "cancelled") {
    const controller = new AbortController();
    setTimeout(() => controller.abort(), 1);
    out = await attempt({ signal: controller.signal });
  } else if (scenario === "timeout") {
    const slow = Bun.serve({ port: 0, fetch: () => new Promise(() => {}) });
    out = await attempt({ baseUrl: `http://127.0.0.1:${slow.port}`, timeoutMs: 120, retries: 0 });
    slow.stop(true);
  } else {
    out = await attempt();
  }
  console.log(JSON.stringify({ scenario, ...(out as Record<string, unknown>) }));
} finally {
  server.stop(true);
}
