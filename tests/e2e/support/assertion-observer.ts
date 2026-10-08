/** Assertion operands from actual behavior cases, never a suite-exit oracle. */
import nativeAssert from "node:assert/strict";
import { AsyncLocalStorage } from "node:async_hooks";
import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { parse } from "@babel/parser";

export interface AssertionObservation {
  operator: string;
  actual: unknown;
  expected: unknown;
  matched: boolean;
  source: string;
  location: string;
  assertionId: string;
  message?: string;
}
export interface ScenarioObservation {
  name: string;
  assertions: AssertionObservation[];
}

const active = new AsyncLocalStorage<ScenarioObservation>();
const cases: ScenarioObservation[] = [];
const ownFile = fileURLToPath(import.meta.url);
const sources = new Map<string, { text: string; lines: string[]; calls: { start: number; end: number; expression: string }[] }>();

function assertionCalls(text: string): { start: number; end: number; expression: string }[] {
  const calls: { start: number; end: number; expression: string }[] = [];
  const visit = (value: unknown): void => {
    if (!value || typeof value !== "object") return;
    if (Array.isArray(value)) { value.forEach(visit); return; }
    const node = value as Record<string, unknown>;
    const callee = node.callee as { type?: string; name?: string; object?: { name?: string } } | undefined;
    if (node.type === "CallExpression" && (callee?.name === "assert" || callee?.object?.name === "assert") &&
        typeof node.start === "number" && typeof node.end === "number") {
      calls.push({ start: node.start, end: node.end, expression: text.slice(node.start, node.end) });
    }
    Object.values(node).forEach(visit);
  };
  visit(parse(text, { sourceType: "module", plugins: ["typescript"] }));
  return calls;
}

function snapshot(value: unknown, seen = new WeakSet<object>()): unknown {
  if (value === undefined) return { kind: "undefined" };
  if (typeof value === "bigint") return { kind: "bigint", value: String(value) };
  if (typeof value === "function") return { kind: "function", name: value.name };
  if (typeof value === "symbol") return { kind: "symbol", value: String(value) };
  if (typeof value === "number" && !Number.isFinite(value)) return { kind: "number", value: String(value) };
  if (typeof value === "string" && value.length > 16000) {
    return { kind: "long-string", length: value.length, sha256: createHash("sha256").update(value).digest("hex") };
  }
  if (!value || typeof value !== "object") return value;
  if (value instanceof Error) return { name: value.name, message: value.message };
  if (value instanceof RegExp) return { kind: "regexp", source: value.source, flags: value.flags };
  if (seen.has(value)) return { kind: "reference" };
  seen.add(value);
  if (Array.isArray(value)) return value.map(item => snapshot(item, seen));
  return Object.fromEntries(Object.entries(value).map(([key, item]) => [key, snapshot(item, seen)]));
}

function origin(): { source: string; location: string; assertionId: string } {
  for (const frame of new Error().stack?.split("\n").slice(1) ?? []) {
    const match = /(?:\(|at )(file:\/\/[^)]+|\/[^)]+):(\d+):(\d+)\)?$/.exec(frame.trim());
    if (!match) continue;
    const file = match[1]!.startsWith("file:") ? fileURLToPath(match[1]!) : match[1]!;
    if (file === ownFile) continue;
    let sourceFile = sources.get(file);
    if (!sourceFile) {
      try { const text = readFileSync(file, "utf8"); sourceFile = { text, lines: text.split("\n"), calls: assertionCalls(text) }; sources.set(file, sourceFile); }
      catch { continue; }
    }
    const offset = sourceFile.lines.slice(0, Number(match[2]) - 1).reduce((sum, line) => sum + line.length + 1, 0) + Number(match[3]) - 1;
    const call = sourceFile.calls.filter(call => call.start <= offset && offset < call.end).sort((a, b) => a.end - a.start - (b.end - b.start))[0];
    if (!call) continue;
    const source = call.expression;
    return { source, location: `${path.relative(process.cwd(), file)}:${match[2]}:${match[3]}`,
      assertionId: createHash("sha256").update(source).digest("hex") };
  }
  return { source: "", location: "unknown", assertionId: "unknown" };
}

const methods = new Set(["ok", "equal", "strictEqual", "notEqual", "notStrictEqual", "deepEqual", "deepStrictEqual",
  "notDeepEqual", "notDeepStrictEqual", "match", "doesNotMatch", "throws", "doesNotThrow", "rejects", "doesNotReject", "fail"]);

function invoke(operator: string, method: Function, args: unknown[]): unknown {
  const scope = active.getStore();
  if (!scope) return Reflect.apply(method, nativeAssert, args);
  const observation: AssertionObservation = { operator, actual: snapshot(args[0]), expected: snapshot(args[1]), matched: false, ...origin() };
  const messageIndex = operator === "ok" ? 1 : 2;
  if (typeof args[messageIndex] === "string") observation.message = args[messageIndex] as string;
  scope.assertions.push(observation);
  const callArgs = [...args];
  if (["throws", "doesNotThrow", "rejects", "doesNotReject"].includes(operator)) {
    const captureError = (error: unknown): never => { observation.actual = snapshot(error); throw error; };
    if (typeof args[0] === "function") {
      callArgs[0] = () => {
        try {
          const result = Reflect.apply(args[0] as Function, undefined, []);
          return operator === "rejects" || operator === "doesNotReject" ? Promise.resolve(result).catch(captureError) : result;
        } catch (error) { return captureError(error); }
      };
    } else if (operator === "rejects" || operator === "doesNotReject") {
      callArgs[0] = Promise.resolve(args[0]).catch(captureError);
    }
  }
  try {
    const result = Reflect.apply(method, nativeAssert, callArgs);
    if (operator === "rejects" || operator === "doesNotReject") {
      return Promise.resolve(result).then(() => { observation.matched = true; });
    }
    observation.matched = true;
    return result;
  } catch (error) { throw error; }
}

/** Same assertion API and failure semantics; records only within a named scope. */
export const observedAssert: typeof nativeAssert = new Proxy(nativeAssert, {
  apply(target, _this, args) { return invoke("ok", target, args); },
  get(target, property, receiver) {
    const value: unknown = Reflect.get(target, property, receiver);
    return typeof property === "string" && methods.has(property) && typeof value === "function"
      ? (...args: unknown[]) => invoke(property, value, args) : value;
  },
});

export function observeScenario<T>(name: string, body: () => T): T {
  const scope: ScenarioObservation = { name, assertions: [] };
  cases.push(scope);
  return active.run(scope, body);
}

export function observedScenarios(): readonly ScenarioObservation[] { return cases; }
