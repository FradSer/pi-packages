/**
 * Deterministic parser for the explicit flag form.
 *
 * Flags are the user's own arithmetic: when every parameter is written out, no
 * model is needed and none is called. The parser reports "not-parameterized"
 * when the request carries no flag, which is the only signal that hands the
 * request to the decision service.
 */

import { DEFAULT_COUNT_INTERVAL_MS, parseDuration } from "./duration.ts";
import { unknownPlaceholder } from "./template.ts";

export interface ParameterizedPlan {
  message: string;
  intervalMs: number;
  maxRuns?: number;
  until?: string;
}

export type ParameterizedParse =
  | { kind: "not-parameterized" }
  | { kind: "invalid"; error: string }
  /** `intervalAssumed` reports a cadence the parser supplied; see duration.ts. */
  | { kind: "plan"; plan: ParameterizedPlan; intervalAssumed?: boolean };

const FLAG_ALIASES: Record<string, string> = {
  "--every": "every",
  "-e": "every",
  "--times": "times",
  "-t": "times",
  "--until": "until",
  "-u": "until",
  "--message": "message",
  "-m": "message",
};

/**
 * Split a command line into tokens, honouring single and double quotes.
 * Return undefined for an unterminated quote, so a stray quote is a reported
 * error instead of a silently mangled message.
 */
export function tokenize(input: string): string[] | undefined {
  const tokens: string[] = [];
  let current = "";
  let quote: string | undefined;
  let hasToken = false;
  let index = 0;
  while (index < input.length) {
    const char = input[index];
    index += 1;
    if (char === undefined) break;
    if (quote !== undefined) {
      if (char === "\\" && quote === "\"") {
        const escaped = input[index];
        if (escaped !== undefined) {
          current += escaped;
          index += 1;
          continue;
        }
      }
      if (char === quote) {
        quote = undefined;
        continue;
      }
      current += char;
      continue;
    }
    if (char === "\"" || char === "'") {
      quote = char;
      hasToken = true;
      continue;
    }
    if (/\s/.test(char)) {
      if (hasToken) {
        tokens.push(current);
        current = "";
        hasToken = false;
      }
      continue;
    }
    current += char;
    hasToken = true;
  }
  if (quote !== undefined) return undefined;
  if (hasToken) tokens.push(current);
  return tokens;
}

function looksLikeFlag(token: string): boolean {
  return FLAG_ALIASES[token] !== undefined || (token.startsWith("--") && token !== "--");
}

/** Parse the explicit flag form, or report that the request does not use it. */
export function parseParameterized(input: string): ParameterizedParse {
  const tokens = tokenize(input);
  if (tokens === undefined) return { kind: "invalid", error: "Unterminated quote in the request." };
  if (!tokens.some(looksLikeFlag)) return { kind: "not-parameterized" };

  const flags = new Map<string, string>();
  const positional: string[] = [];
  let literalOnly = false;
  let index = 0;
  while (index < tokens.length) {
    const token = tokens[index];
    index += 1;
    if (token === undefined) continue;
    if (literalOnly) {
      positional.push(token);
      continue;
    }
    if (token === "--") {
      literalOnly = true;
      continue;
    }
    const equals = token.startsWith("--") ? token.indexOf("=") : -1;
    if (equals > 0) {
      const name = token.slice(0, equals);
      const canonical = FLAG_ALIASES[name];
      if (canonical === undefined) return { kind: "invalid", error: "Unknown option: " + name };
      if (flags.has(canonical)) return { kind: "invalid", error: "Repeated option: " + name };
      flags.set(canonical, token.slice(equals + 1));
      continue;
    }
    const canonical = FLAG_ALIASES[token];
    if (canonical !== undefined) {
      const value = tokens[index];
      if (value === undefined) return { kind: "invalid", error: "Option " + token + " needs a value." };
      if (flags.has(canonical)) return { kind: "invalid", error: "Repeated option: " + token };
      flags.set(canonical, value);
      index += 1;
      continue;
    }
    if (token.startsWith("--")) return { kind: "invalid", error: "Unknown option: " + token };
    positional.push(token);
  }

  const times = flags.get("times")?.trim();
  let maxRuns: number | undefined;
  if (times !== undefined) {
    if (!/^[0-9]+$/.test(times) || Number(times) < 1) {
      return { kind: "invalid", error: "--times must be a whole number of at least 1." };
    }
    maxRuns = Number(times);
  }

  // An unnamed cadence is not a gap: the plan takes the default cadence and the
  // start notice says it was assumed.
  const every = flags.get("every");
  let intervalMs: number;
  let intervalAssumed = false;
  if (every === undefined) {
    intervalMs = DEFAULT_COUNT_INTERVAL_MS;
    intervalAssumed = true;
  } else {
    const parsedInterval = parseDuration(every);
    if (parsedInterval === undefined) {
      return { kind: "invalid", error: "--every must be a duration between 1s and 1d, for example 5m." };
    }
    intervalMs = parsedInterval;
  }

  const messageFlag = flags.get("message");
  if (messageFlag !== undefined && positional.length > 0) {
    return { kind: "invalid", error: "Use --message or trailing text, not both." };
  }
  const message = (messageFlag ?? positional.join(" ")).trim();
  if (!message) return { kind: "invalid", error: "A message is required: add text or --message." };
  const unknown = unknownPlaceholder(message);
  if (unknown !== undefined) return { kind: "invalid", error: "Unknown placeholder: " + unknown };

  const until = flags.get("until")?.trim();
  if (until !== undefined && until === "") {
    return { kind: "invalid", error: "--until needs a condition." };
  }

  const plan: ParameterizedPlan = { message, intervalMs };
  if (maxRuns !== undefined) plan.maxRuns = maxRuns;
  if (until !== undefined) plan.until = until;
  return intervalAssumed ? { kind: "plan", plan, intervalAssumed } : { kind: "plan", plan };
}
