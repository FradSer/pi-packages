import process from "node:process";
import type { SystemOneRequest } from "./questions.ts";

export interface NoulAnswer {
  readonly type: "noul";
  readonly noul: number;
}

export interface ChoiceAnswer {
  readonly type: "choice";
  readonly choice: string;
  readonly probabilities: Readonly<Record<string, number>>;
  readonly confidence: number;
}

export interface ScoreAnswer {
  readonly type: "score";
  readonly score: number;
  readonly legend: Readonly<Record<string, string>>;
  readonly probabilities: Readonly<Record<string, number>>;
  readonly confidence: number;
}

export type ModelAnswer = NoulAnswer | ChoiceAnswer | ScoreAnswer;

export interface ModelResponse {
  readonly model: string;
  readonly answers: Readonly<Record<string, ModelAnswer>>;
  readonly inputTokens?: number;
  readonly outputTokens?: number;
}

export type ErrorCode =
  | "NO_API_KEY"
  | "UNAUTHORIZED"
  | "RATE_LIMITED"
  | "INVALID_REQUEST"
  | "INVALID_RESPONSE"
  | "PROVIDER_FAILED";

/** Every failure carries a code, so the CLI and the command report one line. */
export class TypeSafeError extends Error {
  // No parameter properties: the CLI runs under Node type erasure.
  readonly code: ErrorCode;
  readonly status: number | undefined;

  constructor(message: string, code: ErrorCode, status?: number) {
    super(message);
    this.name = "TypeSafeError";
    this.code = code;
    this.status = status;
  }
}

export interface ClientOptions {
  readonly apiKey?: string | undefined;
  readonly model?: string | undefined;
  readonly endpoint?: string | undefined;
  readonly fetchImpl?: typeof fetch | undefined;
  readonly signal?: AbortSignal | undefined;
}

const DEFAULT_ENDPOINT = "https://api.typesafe.ai/v1/systemone";
const DEFAULT_MODEL = "jev-latest";

function unit(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value) && value >= 0 && value <= 1;
}

function probabilities(value: unknown): Readonly<Record<string, number>> | undefined {
  if (typeof value !== "object" || value === null || Array.isArray(value)) return undefined;
  const entries = Object.entries(value as Record<string, unknown>);
  if (entries.length === 0) return undefined;
  const result: Record<string, number> = {};
  let sum = 0;
  for (const [key, probability] of entries) {
    if (!unit(probability)) return undefined;
    result[key] = probability;
    sum += probability;
  }
  // Probabilities must sum to approximately 1 (allow float rounding tolerance e.g. 0.90 to 1.10)
  if (sum < 0.9 || sum > 1.1) return undefined;
  return result;
}

/** Rejects any answer the rest of the code could not read a value from. */
export function parseAnswers(raw: unknown): Record<string, ModelAnswer> {
  if (typeof raw !== "object" || raw === null) {
    throw new TypeSafeError("The response is not an object.", "INVALID_RESPONSE");
  }
  const rawRecord = raw as Record<string, unknown>;
  if (typeof rawRecord.answers !== "object" || rawRecord.answers === null) {
    throw new TypeSafeError("The response has no valid answers object.", "INVALID_RESPONSE");
  }
  const source = rawRecord.answers as Record<string, unknown>;
  const answers: Record<string, ModelAnswer> = {};
  for (const [id, value] of Object.entries(source)) {
    if (typeof value !== "object" || value === null) {
      throw new TypeSafeError(`The answer for "${id}" is not an object.`, "INVALID_RESPONSE");
    }
    const answer = value as Record<string, unknown>;
    if (answer["type"] === "noul") {
      if (!unit(answer["noul"])) throw new TypeSafeError(`The Noul for "${id}" is outside [0, 1].`, "INVALID_RESPONSE");
      answers[id] = { type: "noul", noul: answer["noul"] };
      continue;
    }
    const distribution = probabilities(answer["probabilities"]);
    if (distribution === undefined) {
      throw new TypeSafeError(`The answer for "${id}" has no valid probability distribution.`, "INVALID_RESPONSE");
    }
    if (answer["type"] === "choice") {
      if (typeof answer["choice"] !== "string") {
        throw new TypeSafeError(`The choice for "${id}" is not a string.`, "INVALID_RESPONSE");
      }
      if (!unit(answer["confidence"])) {
        throw new TypeSafeError(`The confidence for "${id}" is outside [0, 1].`, "INVALID_RESPONSE");
      }
      answers[id] = {
        type: "choice",
        choice: answer["choice"],
        probabilities: distribution,
        confidence: answer["confidence"],
      };
      continue;
    }
    if (answer["type"] === "score") {
      const score = answer["score"];
      if (typeof score !== "number" || !Number.isFinite(score)) {
        throw new TypeSafeError(`The score for "${id}" is not a number.`, "INVALID_RESPONSE");
      }
      const rawLegend = (answer["legend"] ?? {}) as Record<string, unknown>;
      const legend: Record<string, string> = {};
      for (const [lvl, desc] of Object.entries(rawLegend)) {
        if (typeof desc !== "string") {
          throw new TypeSafeError(`The legend for level "${lvl}" in "${id}" is not a string.`, "INVALID_RESPONSE");
        }
        legend[lvl] = desc;
      }
      answers[id] = { type: "score", score, legend, probabilities: distribution, confidence: unit(answer["confidence"]) ? answer["confidence"] : 0 };
      continue;
    }
    throw new TypeSafeError(`The answer type "${String(answer["type"])}" for "${id}" is not supported.`, "INVALID_RESPONSE");
  }
  return answers;
}

function statusError(status: number, body: string): TypeSafeError {
  if (status === 401) return new TypeSafeError("The TypeSafe API key was rejected.", "UNAUTHORIZED", status);
  if (status === 422) return new TypeSafeError(`The request was rejected: ${body.slice(0, 200)}`, "INVALID_REQUEST", status);
  if (status === 429 || status === 529) {
    return new TypeSafeError(`The TypeSafe API is busy (${status}); retry later.`, "RATE_LIMITED", status);
  }
  return new TypeSafeError(`The TypeSafe API answered ${status}.`, "PROVIDER_FAILED", status);
}

/**
 * One call to the TypeSafe evaluation endpoint. The API key is read from the
 * environment only, never from a flag, so a key cannot end up in a transcript.
 */
export async function systemOne(options: ClientOptions, request: SystemOneRequest): Promise<ModelResponse> {
  const apiKey = options.apiKey ?? process.env["TYPESAFE_API_KEY"];
  if (apiKey === undefined || apiKey === "") {
    throw new TypeSafeError("Set TYPESAFE_API_KEY to judge clauses with Jev.", "NO_API_KEY");
  }
  const doFetch = options.fetchImpl ?? fetch;
  let response: Response;
  try {
    response = await doFetch(options.endpoint ?? DEFAULT_ENDPOINT, {
      method: "POST",
      headers: { Authorization: `Bearer ${apiKey}`, "Content-Type": "application/json" },
      body: JSON.stringify({ model: options.model ?? DEFAULT_MODEL, ...request }),
      ...(options.signal === undefined ? {} : { signal: options.signal }),
    });
  } catch (error) {
    throw new TypeSafeError(`The TypeSafe API call failed: ${(error as Error).message}`, "PROVIDER_FAILED");
  }
  const body = await response.text();
  if (!response.ok) throw statusError(response.status, body);
  let parsed: unknown;
  try {
    parsed = JSON.parse(body);
  } catch {
    throw new TypeSafeError("The TypeSafe API answered with a body that is not JSON.", "INVALID_RESPONSE");
  }
  const record = parsed as Record<string, unknown>;
  const usage = (record["usage"] ?? {}) as Record<string, unknown>;
  return {
    model: typeof record["model"] === "string" ? record["model"] : (options.model ?? DEFAULT_MODEL),
    answers: parseAnswers(record),
    ...(typeof usage["input_tokens"] === "number" ? { inputTokens: usage["input_tokens"] } : {}),
    ...(typeof usage["output_tokens"] === "number" ? { outputTokens: usage["output_tokens"] } : {}),
  };
}
